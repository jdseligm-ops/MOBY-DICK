"""OBD-17kt geo-IBD baseline: the per-example chain, shared by training and inference.

Design: projects/OBD17kt_ml/docs/MODEL_DESIGN.md (the full-size chain); this is the compact version (one skops file).
  [A] pulse finding + Layout-B2 rows (layoutb.compile_rows): one row per pulse onset = own + 6 neighbour + ring-2 waveforms
  Stage 1  hit cleaner RF on the rows -> hard cut p >= p_cut (keeps ~95 % of real light)
  Stage 2  flash classifier RF per readout window (multi-resolution time profile, bands, ratios, 204 patches, light)
  Stage 3  per-pulse distance-to-source regressor (HistGradientBoosting, L1) + forward-model triangulation per window
  Stage 4  pair RF: IBD / (alpha,n) / accidental; score = P(IBD)
  Position calibration (MODEL_DESIGN.md section 14): delta-rho / delta-z regressors applied to the OUTPUT positions only
Every function here reads only the published waveform files (and, for training targets, the published labels).
"""
import numpy as np
from scipy.optimize import least_squares

import digitize as dg
import layoutb as lb

CFG = dg.DigiConfig()
S_NS, NS = CFG.sample_ns, CFG.n_samples
NWAVE = lb.N_BLOCKS * (lb.PRE + lb.POST)
KEEP_EXTRA = [0, 1, 2, 3, 6]          # t_onset_minus_trig_ns, onset_rank, is_wall, z_over_25m, rho_over_15m
PROMPT_LO, PROMPT_HI = -5, 20         # samples around window 0's trigger (prompt_nhit)
R_MAX, Z_MAX = 12.0, 22.0             # target volume (m)
SCALE = 1.6                           # centroid -> vertex start value
MR_EDGES = np.array([0, 15, 30] + list(range(45, 100)) + list(range(100, 148, 4)) + list(range(148, 300, 16)) + [300])
BANDS = [(0, 45), (45, 75), (75, 125), (125, 300)]
N_PATCH = 204
N_S2 = 7                              # positron, li6_capture, h_capture, overlap, radioactive_single, alpha_single, proton_recoil
IBD_SAMPLES = {"geoU", "geoTh", "reactor"}
CLASS4 = {0: 0, 1: 0, 2: 0, 3: 1, 4: 2}  # dataset cls -> Stage-4 class (IBD, alpha_n, accidental)
S4_NAMES = ([f"p_prompt_{c}" for c in range(7)] + [f"p_delayed_{c}" for c in range(7)] +
            ["q_prompt", "q_delayed", "npulse_prompt", "npulse_delayed", "prompt_nhit", "dt_ns", "dR_m",
             "rho_prompt_m", "absz_prompt_m", "rho_delayed_m", "absz_delayed_m", "cent_shift_prompt_m", "cent_shift_delayed_m", "n_windows",
             # prompt-capture consistency (user decision 2026-11-14): mean soft-L1 cost of one window's per-pulse
             # distances at the OTHER window's fit minus at its own fit; ~0 for a real IBD (capture ~cm from the vertex)
             "cons_delayed_at_prompt", "cons_prompt_at_delayed", "cost_prompt_own", "cost_delayed_own"])
# standard (conventional) reconstruction, reported per example for the comparison with classical methods
STD_NAMES = ["E_prompt_pe", "E_delayed_pe", "dt_ns",
             "prompt_x_raw", "prompt_y_raw", "prompt_z_raw", "capture_x_raw", "capture_y_raw", "capture_z_raw",
             "prompt_ok", "prompt_nll", "prompt_n_pmt", "capture_ok", "capture_nll", "capture_n_pmt",
             "dark_pe_per_ns_prompt", "dark_pe_per_ns_capture"]
STD_NAMES = STD_NAMES + ["clean_" + n for n in STD_NAMES]   # the same conventional fit on Stage-1-kept hits only (ablation)
# Physics features for Stage 4 (PLAN_SELECTION_PHYSICS.md B1-B6; Gatti approved by the user 2026-11-14)
PSD_EDGES = np.arange(-12.0, 300.0 + 4.0, 4.0)       # ns, TOF-corrected time relative to the flash start (78 bins)
N_PSD = len(PSD_EDGES) - 1
TTR_ALL, TTR_TAIL = (-10.0, 300.0), (30.0, 300.0)    # tail-to-total windows (ns)
PX_NAMES = ["ttr_prompt", "ttr_delayed", "E_prompt_tof_pe", "E_delayed_tof_pe", "dt_fit_ns", "wall_dist_prompt_m", "asym_prompt"]
S4X_EXTRA = PX_NAMES + ["gatti_prompt", "gatti_delayed"]
STD_E_WINDOW_NS = (-50.0, 250.0)      # energy = charge with time residual in this range at the fitted vertex, minus dark
STD_DARK_NS = (-200.0, -60.0)         # pre-trigger interval (relative to the window trigger) for the dark-charge density
CAL_COLS = ["q_prompt", "q_delayed", "npulse_prompt", "npulse_delayed", "prompt_nhit", "dt_ns", "dR_m",
            "cent_shift_prompt_m", "cent_shift_delayed_m", "n_windows"]


def pulse_area_samples(n_phase=40):
    k = np.arange(int(np.ceil(CFG.pulse_len_ns / CFG.sample_ns)) + 1)
    return float(np.mean([dg.pulse_shape(k * CFG.sample_ns + ph, CFG).sum() for ph in np.linspace(0, CFG.sample_ns, n_phase, endpoint=False)]))


AREA = pulse_area_samples()


def patch_ids(px, py, pz, pw):
    wall = np.abs(pw) < 0.5
    pid = np.zeros(len(px), np.int64)
    z_half = np.abs(pz[wall]).max() + 1.0
    zb = np.clip(((pz + z_half) / (2 * z_half) * 10).astype(int), 0, 9)
    phi = np.arctan2(py, px)
    pb16 = np.clip(((phi + np.pi) / (2 * np.pi) * 16).astype(int), 0, 15)
    pid[wall] = (zb * 16 + pb16)[wall]
    rho = np.hypot(px, py)
    R = rho[~wall].max() + 1.0
    r1, r2 = R * np.sqrt(1 / 22), R * np.sqrt(8 / 22)
    ring = np.where(rho < r1, 0, np.where(rho < r2, 1, 2))
    sec7 = np.clip(((phi + np.pi) / (2 * np.pi) * 7).astype(int), 0, 6)
    sec14 = np.clip(((phi + np.pi) / (2 * np.pi) * 14).astype(int), 0, 13)
    local = np.where(ring == 0, 0, np.where(ring == 1, 1 + sec7, 8 + sec14))
    top = pz > 0
    pid[~wall & top] = 160 + local[~wall & top]
    pid[~wall & ~top] = 182 + local[~wall & ~top]
    return pid


class Geometry:
    def __init__(self, path):
        import h5py
        with h5py.File(path, "r") as g:
            self.px, self.py, self.pz = (g[k][()].astype(np.float64) for k in ("x", "y", "z"))
            u, v, w = g["u"][()], g["v"][()], g["w"][()]
        self.nbt, self.wall, self.ring2 = lb.neighbour_table(self.px, self.py, self.pz, u, v, w)
        self.pid = patch_ids(self.px, self.py, self.pz, w.astype(np.float64))
        self.P = np.column_stack([self.px, self.py, self.pz]) / 1000.0


def rows(res, G, with_truth=False):
    """Layout-B2 rows of one example. Returns X, y (truth or None), wn, pmt, k_on (absolute window sample), src."""
    meta = {}
    X, y, _, wn = lb.compile_rows(res, G.nbt, G.wall, (G.px, G.py, G.pz), CFG, with_truth=with_truth, ring2=G.ring2, meta=meta)
    if len(X) == 0:
        return X, y, wn, np.zeros(0, np.int64), np.zeros(0, np.int64), None
    pmt = np.concatenate(meta["pmt"])
    k_on = np.rint(X[:, NWAVE] / S_NS).astype(int) + res["win_trig"][wn].astype(int)
    src = np.concatenate(meta["src"]) if with_truth else None
    return X, y, wn, pmt, k_on, src


def forest_proba(rf, X):
    """RandomForestClassifier.predict_proba without the per-call validation/joblib overhead (the hot path runs it
    ~10^5 times). Same arithmetic: each tree's leaf class fractions, normalised, summed in tree order, divided by n."""
    X = np.ascontiguousarray(X, dtype=np.float32)
    out = np.zeros((len(X), rf.n_classes_))
    for est in rf.estimators_:
        p = est.tree_.predict(X)
        p = (p[:, 0, :] if p.ndim == 3 else p)[:, :rf.n_classes_]
        nrm = p.sum(axis=1); nrm[nrm == 0.0] = 1.0
        out += p / nrm[:, None]
    return out / len(rf.estimators_)


def pulse_charge(X):
    return np.clip(X[:, lb.PRE - 2:lb.PRE + 12].sum(axis=1), 0, None) / (CFG.adc_per_pe * AREA)


def dist_features(X, wn, q):
    """Distance-model inputs: 256 waveform samples + 5 position-invariant extras + window charge + window pulse count."""
    wq = np.zeros(len(X)); wnum = np.zeros(len(X))
    for w in np.unique(wn):
        m = wn == w
        wq[m] = q[m].sum(); wnum[m] = m.sum()
    return np.hstack([X[:, :NWAVE], X[:, NWAVE + np.array(KEEP_EXTRA)], wq[:, None], wnum[:, None]]).astype(np.float32)


def window_s2_features(k_on, q, pmt, m, G):
    prof = np.zeros(NS); patch = np.zeros(N_PATCH)
    np.add.at(prof, np.clip(k_on[m], 0, NS - 1), q[m]); np.add.at(patch, G.pid[pmt[m]], q[m])
    mr = np.add.reduceat(prof, MR_EDGES[:-1])
    bands = np.array([prof[b0:b1].sum() for b0, b1 in BANDS])
    sig = bands[1:].sum()
    ratios = bands[2:] / sig if sig > 0 else np.zeros(2)
    return np.concatenate([mr, bands, ratios, patch, [sig, int(m.sum())]]).astype(np.float32), float(sig)


def window_class(sample, w, n_win_real, n_target, win_start_ns):
    """Stage-2 truth class of one window (the same rule as the full chain, stage2_rows.window_class)."""
    p, d = n_win_real
    tot = max(p + d, 1)
    fp, fd = p / tot, d / tot
    cap = 1 if n_target == 1 else (2 if n_target == 2 else -1)
    if sample in IBD_SAMPLES:
        if fd < 0.10:
            return 0
        if fp < 0.10:
            return cap
        return 3
    if sample == "alphan":
        if win_start_ns > 1e6:
            return 4
        if w == 0 or fp >= 0.10:
            return 6
        return cap
    if sample == "po210_ls":
        return 5
    if sample == "bipo214_ls":
        return 5 if w == 1 else 4
    return 4


def window_truth_classes(res, truth_e):
    """Per-window Stage-2 classes for one published example (truth_e: that example's truth fields)."""
    cls = int(truth_e["cls"]); nt = int(truth_e["n_target"])
    sa, sb = str(truth_e["sample_a"]), str(truth_e["sample_b"])
    out = []
    for w in range(len(res["win_start"])):
        labw = res["pe_label"][res["pe_win"] == w]
        p, d = int((labw == 1).sum()), int((labw == 2).sum())
        if cls == 4:                                   # accidental: each window comes from one of two singles
            out.append(window_class(sa if p >= d else sb, w, (p, d), -1, 0.0))
        else:
            out.append(window_class(sa, w, (p, d), nt, float(res["win_start"][w]) * S_NS))
    return out


def prompt_nhit(X, wn, pmt):
    """Prompt size: PMTs with a pulse onset in [PROMPT_LO, PROMPT_HI) samples of window 0's trigger (from the rows)."""
    if len(X) == 0:
        return 0
    k = np.rint(X[:, NWAVE] / S_NS)
    m = (wn == 0) & (k >= PROMPT_LO) & (k < PROMPT_HI)
    return int(len(np.unique(pmt[m])))


def fit_vertex(P, d, v0, fwd):
    """Triangulation with the forward model: residual (d_pred - g(|v - P|)) / sigma(|v - P|), soft-L1, bounded,
    analytic Jacobian (g and sigma are piecewise linear)."""
    c, g, sg = fwd
    dg_ = np.diff(g) / np.diff(c); ds_ = np.diff(sg) / np.diff(c)

    def parts(v):
        D = v - P
        r = np.maximum(np.linalg.norm(D, axis=1), 1e-9)
        return D, r, np.interp(r, c, g), np.interp(r, c, sg)

    def resid(v):
        _, _, gr, sr = parts(v)
        return (d - gr) / sr

    def jac(v):
        D, r, gr, sr = parts(v)
        j = np.clip(np.searchsorted(c, r) - 1, 0, len(c) - 2)
        inside = (r > c[0]) & (r < c[-1])
        gp = np.where(inside, dg_[j], 0.0); sp = np.where(inside, ds_[j], 0.0)
        dres_dr = (-gp * sr - (d - gr) * sp) / sr ** 2
        return dres_dr[:, None] * D / r[:, None]
    lo, hi = np.array([-R_MAX, -R_MAX, -Z_MAX]), np.array([R_MAX, R_MAX, Z_MAX])
    v0 = np.clip(v0, lo + 1e-3, hi - 1e-3)
    return least_squares(resid, v0, jac=jac, loss="soft_l1", f_scale=1.0, bounds=(lo, hi), max_nfev=200).x


def flash_start(tc, width=20.0, step=1.0):
    """Start of the densest `width` ns interval of TOF-corrected times (the flash onset)."""
    return trigger_time(tc, width, step)


def tof_profile(tle, q, Pp, v, v_g, dark_per_ns, subtract_dark=False):
    """B1/B2/B3: TOF-corrected pulse times t - |P - v| / v_g relative to the flash start; returns the normalised charge
    histogram on PSD_EDGES, the tail-to-total ratio, the flash start (ns, window-trigger frame) and the dark-subtracted
    charge in TTR_ALL."""
    if len(tle) < 10:
        return np.zeros(N_PSD), 0.0, 0.0, 0.0
    tc = tle - np.linalg.norm(Pp - v, axis=1) / v_g
    t0 = flash_start(tc)
    rel = tc - t0
    allw = (rel >= TTR_ALL[0]) & (rel < TTR_ALL[1])
    h = np.histogram(rel, bins=PSD_EDGES, weights=q)[0]
    tot = float(q[allw].sum()); tail = float(q[(rel >= TTR_TAIL[0]) & (rel < TTR_TAIL[1])].sum())
    E = tot - dark_per_ns * (TTR_ALL[1] - TTR_ALL[0])
    if subtract_dark:      # variant v5 (review 2026-11-14): subtract the measured dark density per bin/window
        h = h - dark_per_ns * np.diff(PSD_EDGES)
        tot, tail = E, tail - dark_per_ns * (TTR_TAIL[1] - TTR_TAIL[0])
    return h / max(h.sum(), 1e-9), tail / max(tot, 1e-9), float(t0), float(E)


def outward_asymmetry(Pp, q, v):
    """B5: charge-weighted mean direction from the vertex to the hit PMTs, projected on the radial unit vector at v."""
    if len(q) < 10:
        return 0.0
    u = Pp - v
    u /= np.maximum(np.linalg.norm(u, axis=1), 1e-9)[:, None]
    rho = np.hypot(v[0], v[1])
    rhat = np.array([v[0] / rho, v[1] / rho, 0.0]) if rho > 1e-6 else np.zeros(3)
    return float(((q[:, None] * u).sum(0) / max(q.sum(), 1e-9)) @ rhat)


def window_cost(P, d, v, fwd):
    """Mean soft-L1 cost of the per-pulse distance residuals at point v (the fit_vertex objective, per pulse)."""
    c, g, sg = fwd
    r = np.linalg.norm(P - v, axis=1)
    z = ((d - np.interp(r, c, g)) / np.interp(r, c, sg)) ** 2
    return float(np.mean(2.0 * (np.sqrt(1.0 + z) - 1.0)))


def leading_edge_ns(X):
    """Interpolated threshold-crossing time of each row's pulse (ns, relative to its window's trigger)."""
    v0, v1 = X[:, lb.PRE - 1].astype(np.float64), X[:, lb.PRE].astype(np.float64)
    frac = np.clip((CFG.zs_threshold_adc - v0) / np.maximum(v1 - v0, 1e-9), 0.0, 1.0)
    return (X[:, NWAVE] / S_NS - 1.0 + frac) * S_NS


def first_hits(t, pmt, q, return_index=False):
    """Per PMT: earliest leading edge and total charge (all pulses: the conventional analysis does no hit cleaning)."""
    o = np.lexsort((t, pmt))
    p, tt, qq = pmt[o], t[o], q[o]
    first = np.concatenate(([True], p[1:] != p[:-1]))
    grp = np.cumsum(first) - 1
    if return_index:
        return p[first], tt[first], np.bincount(grp, weights=qq), o[first]
    return p[first], tt[first], np.bincount(grp, weights=qq)


STD_Q_EDGES = np.array([0.0, 1.5, 2.5, 4.5, np.inf])   # first-hit PDFs per PMT-charge class (PE): 1, 2, 3-4, 5+


def trigger_time(t, width=60.0, step=4.0):
    """Classical trigger-time estimate: the start of the sliding `width` ns window holding the most first hits.
    With ~0.5 dark hits/ns over the window, the event's light gives an unambiguous peak."""
    if len(t) == 0:
        return 0.0
    ts = np.sort(t)
    starts = np.arange(ts[0], ts[-1] + step, step)
    counts = np.searchsorted(ts, starts + width) - np.searchsorted(ts, starts)
    return float(starts[int(np.argmax(counts))])


def std_fit(P, t, qp, tpdf):
    """Conventional vertex: time-residual maximum likelihood (KamLAND/Borexino style) with charge-dependent PDFs.
    res_i = t_i - t0 - |v - P_i| / v_eff; -log L = -sum log f_{c(q_i)}(res_i), f_c = the first-hit residual PDF for PMTs
    with charge class c, measured on train truth (scintillation + TTS + scattering + a flat dark-noise floor).
    Start: charge centroid x SCALE, t0 from the median residual. Returns (v, t0, nll, converged)."""
    from scipy.optimize import minimize
    x, LF, v_eff = tpdf["x"], np.atleast_2d(tpdf["logf"]), float(tpdf["v_eff"])
    cls = np.clip(np.searchsorted(STD_Q_EDGES, qp, side="right") - 1, 0, len(LF) - 1)
    slope = np.diff(LF, axis=1) / np.diff(x)[None, :]
    nb = len(x)
    lo, hi = np.array([-R_MAX, -R_MAX, -Z_MAX]), np.array([R_MAX, R_MAX, Z_MAX])
    # seed: hits near the trigger-time peak (sliding window) give the centroid and the t0 start; this keeps t0 off
    # the dark-noise plateau (review by the SIDERIUS instance, 2026-11-14)
    tp = trigger_time(t)
    near = (t >= tp - 20.0) & (t < tp + 100.0)
    if near.sum() < 5:
        near = np.ones(len(t), bool)
    cent = (qp[near, None] * P[near]).sum(0) / max(qp[near].sum(), 1e-9) * SCALE
    v0 = np.clip(cent, lo + 1e-3, hi - 1e-3)
    dx = x[1] - x[0]

    def nll(p):
        v, t0 = p[:3], p[3]
        D = v - P
        r = np.maximum(np.linalg.norm(D, axis=1), 1e-9)
        res = t - t0 - r / v_eff
        u = np.clip((res - x[0]) / dx, 0.0, nb - 1 - 1e-9)                # uniform grid: linear interpolation by index
        j = u.astype(np.int64); fr = u - j
        L = LF[cls, j] * (1 - fr) + LF[cls, np.minimum(j + 1, nb - 1)] * fr
        dl = np.where((res > x[0]) & (res < x[-1]), slope[cls, np.minimum(j, nb - 2)], 0.0)
        return -L.sum(), np.concatenate([(dl[:, None] * (D / r[:, None]) / v_eff).sum(0), [dl.sum()]])
    # t0 start: scan a grid around the trigger-time seed at the start vertex, keep the best, then fit everything
    t_c = float(np.median(t[near] - np.linalg.norm(P[near] - v0, axis=1) / v_eff))
    grid = t_c + np.arange(-100.0, 100.0 + 5.0, 5.0)
    t00 = float(grid[int(np.argmin([nll(np.concatenate([v0, [g]]))[0] for g in grid]))])
    b = [(lo[i] + 1e-3, hi[i] - 1e-3) for i in range(3)] + [(None, None)]
    r = minimize(nll, np.concatenate([v0, [t00]]), jac=True, method="L-BFGS-B", bounds=b, options={"maxiter": 300})
    return r.x[:3], float(r.x[3]), float(r.fun), bool(r.success)


def std_window(X, tle, pmt, q, ma, G, tpdf, v_g=None, dark_sub=False):
    """Conventional analysis of one window: vertex fit on first hits of ALL pulses, then the energy = charge of all
    pulses with residual in STD_E_WINDOW_NS minus the dark charge expected there (density from the pre-trigger interval)."""
    if ma.sum() < 10:
        return {"E": 0.0, "v": np.zeros(3), "t0": 0.0, "nll": 0.0, "ok": False, "n": 0, "dark": 0.0, "hist": np.zeros(N_PSD), "ttr": 0.0}
    hp, ht, hq = first_hits(tle[ma], pmt[ma], q[ma])
    v, t0, f, ok = std_fit(G.P[hp], ht, hq, tpdf)
    res = tle[ma] - t0 - np.linalg.norm(G.P[pmt[ma]] - v, axis=1) / float(tpdf["v_eff"])
    pre = (tle[ma] >= STD_DARK_NS[0]) & (tle[ma] < STD_DARK_NS[1])
    dark = float(q[ma][pre].sum() / (STD_DARK_NS[1] - STD_DARK_NS[0]))
    inw = (res >= STD_E_WINDOW_NS[0]) & (res < STD_E_WINDOW_NS[1])
    E = float(q[ma][inw].sum() - dark * (STD_E_WINDOW_NS[1] - STD_E_WINDOW_NS[0]))
    hist, ttr = np.zeros(N_PSD), 0.0
    if v_g is not None:
        hist, ttr, _, _ = tof_profile(tle[ma], q[ma], G.P[pmt[ma]], v, v_g, dark, dark_sub)
    return {"E": E, "v": v, "t0": t0, "nll": f, "ok": ok, "n": int(len(hp)), "dark": dark, "hist": hist, "ttr": ttr}


def chain_example(res, G, M):
    """Full inference on one example. M: s1, p_cut, s2, dist, fwd0, fwd1 (+ tpdf for the conventional fit).
    Returns (S4 features, prompt fit, capture fit, conventional-analysis vector STD_NAMES)."""
    X, _, wn, pmt, k_on, _ = rows(res, G)
    nw = len(res["win_start"])
    win = {}
    std = {}
    if len(X):
        keep = forest_proba(M["s1"], X)[:, 1] >= M["p_cut"]
        q = pulse_charge(X)
        dpred = np.full(len(X), np.nan)
        if keep.any():
            dpred[keep] = M["dist"].predict(dist_features(X, wn, q)[keep])
        feats = [window_s2_features(k_on, q, pmt, (wn == w) & keep, G) for w in range(nw)]
        P2 = np.zeros((nw, N_S2)); P2[:, M["s2"].classes_] = forest_proba(M["s2"], np.vstack([f for f, _ in feats]))
        tle_all = leading_edge_ns(X)
        tle = tle_all if M.get("want_std") else None
        v_g = M.get("v_g")
        for w in range(nw):
            m = (wn == w) & keep
            p2, sig = P2[w], feats[w][1]
            fw = M["fwd0"] if w == 0 else M["fwd1"]
            if m.sum() >= 10:
                cent = (q[m, None] * G.P[pmt[m]]).sum(0) / max(q[m].sum(), 1e-9) * SCALE
                v = fit_vertex(G.P[pmt[m]], dpred[m], cent, fw)
            else:
                cent = v = np.zeros(3)
            win[w] = {"p2": p2, "q": sig, "np": int(m.sum()), "fit": v, "cent": cent, "P": G.P[pmt[m]], "d": dpred[m], "fw": fw}
            if v_g is not None and m.sum() >= 10:      # B1-B3, B5 on Stage-1-kept pulses at the Stage-3 fit
                pre = m & (tle_all >= STD_DARK_NS[0]) & (tle_all < STD_DARK_NS[1])
                dark = float(q[pre].sum() / (STD_DARK_NS[1] - STD_DARK_NS[0]))
                hist, ttr, t0f, Ef = tof_profile(tle_all[m], q[m], G.P[pmt[m]], v, v_g, dark, M.get("psd_dark_sub", False))
                win[w].update({"hist": hist, "ttr": ttr, "t0f": t0f, "Ef": Ef, "asym": outward_asymmetry(G.P[pmt[m]], q[m], v)})
            if tle is not None:
                std[w] = std_window(X, tle, pmt, q, wn == w, G, M["tpdf"], v_g, M.get("psd_dark_sub", False))
                std[("clean", w)] = std_window(X, tle, pmt, q, (wn == w) & keep, G, M["tpdf"], v_g, M.get("psd_dark_sub", False))
    if 0 not in win:
        win[0] = {"p2": np.zeros(N_S2), "q": 0.0, "np": 0, "fit": np.zeros(3), "cent": np.zeros(3), "P": np.zeros((0, 3)), "d": np.zeros(0), "fw": M["fwd0"]}
    wp = win[0]; wd = win.get(1, win[0])
    dt = float((res["win_start"][1] - res["win_start"][0]) * S_NS + (int(res["win_trig"][1]) - int(res["win_trig"][0])) * S_NS) if nw > 1 else 0.0
    rho = lambda v: float(np.hypot(v[0], v[1]))
    cost = lambda W, v: window_cost(W["P"], W["d"], v, W["fw"]) if W["np"] >= 10 else 0.0
    c_pp, c_dd = cost(wp, wp["fit"]), cost(wd, wd["fit"])
    c_dp, c_pd = (cost(wd, wp["fit"]), cost(wp, wd["fit"])) if 1 in win else (c_dd, c_pp)
    f4 = np.concatenate([wp["p2"], wd["p2"], [wp["q"], wd["q"], wp["np"], wd["np"], prompt_nhit(X, wn, pmt), dt,
                                              float(np.linalg.norm(wp["fit"] - wd["fit"])), rho(wp["fit"]), abs(wp["fit"][2]), rho(wd["fit"]), abs(wd["fit"][2]),
                                              float(np.linalg.norm(wp["cent"] - wp["fit"])), float(np.linalg.norm(wd["cent"] - wd["fit"])), nw,
                                              c_dp - c_dd, c_pd - c_pp, c_pp, c_dd]]).astype(np.float64)
    empty = {"E": 0.0, "v": np.zeros(3), "t0": 0.0, "nll": 0.0, "ok": False, "n": 0, "dark": 0.0, "hist": np.zeros(N_PSD), "ttr": 0.0}
    t_abs = lambda w, st: (float(res["win_start"][w]) + float(res["win_trig"][w])) * S_NS + st["t0"]

    def vec(k0, k1):
        s0 = std.get(k0, empty); s1 = std.get(k1, s0)
        dt_std = t_abs(1, s1) - t_abs(0, s0) if (k0 in std and k1 in std) else 0.0
        return [s0["E"], s1["E"], dt_std, *s0["v"], *s1["v"], s0["ok"], s0["nll"], s0["n"], s1["ok"], s1["nll"], s1["n"], s0["dark"], s1["dark"]]
    sv = np.array(vec(0, 1) + vec(("clean", 0), ("clean", 1)), np.float64) if std else np.full(len(STD_NAMES), np.nan)
    # physics extras (PX_NAMES) + the prompt/delayed TOF profiles (for the Gatti statistic, computed with trained weights)
    g = lambda W, k, d: W.get(k, d)
    two = 1 in win
    dt_fit = (t_abs(1, {"t0": g(wd, "t0f", 0.0)}) - t_abs(0, {"t0": g(wp, "t0f", 0.0)})) if (two and "t0f" in wp and "t0f" in wd) else 0.0
    vp = wp["fit"]
    wall = float(min(R_MAX - np.hypot(vp[0], vp[1]), Z_MAX - abs(vp[2]))) if wp["np"] >= 10 else 0.0
    px = np.concatenate([[g(wp, "ttr", 0.0), g(wd, "ttr", 0.0) if two else 0.0, g(wp, "Ef", 0.0), g(wd, "Ef", 0.0) if two else 0.0, dt_fit, wall,
                          g(wp, "asym", 0.0)], g(wp, "hist", np.zeros(N_PSD)), g(wd, "hist", np.zeros(N_PSD)) if two else np.zeros(N_PSD)])
    s0 = std.get(0, {}); s0c = std.get(("clean", 0), {})
    sh = np.concatenate([[s0.get("ttr", np.nan), s0c.get("ttr", np.nan)], s0.get("hist", np.full(N_PSD, np.nan)), s0c.get("hist", np.full(N_PSD, np.nan))])
    return f4, np.asarray(wp["fit"], np.float64), np.asarray(wd["fit"], np.float64), sv, px, sh


def gatti_weights(r_e, r_p, floor):
    """Gatti & De Martini (1962) linear filter weights w = (r_p - r_e) / (r_p + r_e) from reference shapes, each with a
    flat dark-noise floor added (our addition). Approved by the user as an INPUT feature (2026-11-14)."""
    a, b = r_e + floor, r_p + floor
    return (b - a) / (b + a)


def stage4_matrix(F4, PX, M):
    """Stage-4 input = S4_NAMES features + PX_NAMES physics extras + the Gatti statistic of both windows."""
    hp, hd = PX[:, len(PX_NAMES):len(PX_NAMES) + N_PSD], PX[:, len(PX_NAMES) + N_PSD:]
    w = M["gatti_w"]
    return np.hstack([F4, PX[:, :len(PX_NAMES)], (hp @ w)[:, None], (hd @ w)[:, None]])


def calib_features(F4, pf, cf):
    """Position-calibration inputs (no truth): fitted cylinder coordinates of both windows + light/window features."""
    idx = [S4_NAMES.index(k) for k in CAL_COLS]
    return np.column_stack([np.hypot(pf[:, 0], pf[:, 1]), pf[:, 2], np.abs(pf[:, 2]), np.hypot(cf[:, 0], cf[:, 1]), cf[:, 2], np.abs(cf[:, 2]), F4[:, idx]])


def apply_calibration(F4, pf, cf, cal_r, cal_z):
    rho = np.hypot(pf[:, 0], pf[:, 1]); phi = np.arctan2(pf[:, 1], pf[:, 0])
    C = calib_features(F4, pf, cf)
    rho2 = np.clip(rho + cal_r.predict(C), 0, R_MAX); z2 = np.clip(pf[:, 2] + cal_z.predict(C), -Z_MAX, Z_MAX)
    return np.column_stack([rho2 * np.cos(phi), rho2 * np.sin(phi), z2])
