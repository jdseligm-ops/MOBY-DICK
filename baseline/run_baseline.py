#!/usr/bin/env python3
"""OBD-17kt geo-IBD task: standalone baseline (SIDERIUS Track-1 kit, SPEC section 4.1).

    run_baseline.py train    --data_dir D --seed S --output_dir O
    run_baseline.py evaluate --data_dir D --model M --output_dir O

D is the folder fetch_data.py wrote (train_NNN.h5 + labels, val_NNN.h5 + labels, pmt_geometry.h5).
train   : trains the compact chain (obd_chain.py) from the published train files only, writes O/final_model.skops,
          then evaluates it on the validation group (O/metrics.json, O/predictions.json, O/train_log.json).
evaluate: loads M, runs the chain on every validation example, and writes O/metrics.json (exactly the task's declared
          metric ids, computed by the task's own metric plugins), O/predictions.json and O/metrics_bootstrap.json.
Every random choice uses --seed. Model fits run single-threaded where thread count could change results; the
per-example chain runs in a process pool and its results are collected in example order, so the output does not
depend on the number of cores.
"""
import argparse
import glob
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import h5py  # noqa: E402
import numpy as np  # noqa: E402
from threadpoolctl import threadpool_limits  # noqa: E402

import obd_chain as oc  # noqa: E402
from h5reader import WaveformFile  # noqa: E402

TASK_YAML = os.path.join(HERE, "..", "task", "task.yaml")
HP = {
    "subsets_per_class": {                 # train examples per dataset class (geoU, geoTh, reactor, alphan, accidental)
        "stage1": [400, 150, 250, 300, 500],
        "stage2_dist": [700, 250, 450, 600, 1000],
        "stage4_calibration": [4000, 1500, 2500, 12000, 30000],     # B4: more (alpha,n) and accidentals for the S/B = 1 tail
    },
    "stage1": {"rows_per_example": 300, "holdout_fraction": 0.2, "keep_real_fraction": 0.95,
               "rf": {"n_estimators": 40, "max_leaf_nodes": 256, "min_samples_leaf": 20, "max_features": "sqrt"}},
    "stage2": {"rf": {"n_estimators": 40, "max_leaf_nodes": 128, "min_samples_leaf": 3, "max_features": "sqrt",
                      "class_weight": "balanced_subsample"}},
    "dist": {"rows_per_example": 200, "holdout_fraction": 0.2, "forward_bin_m": 1.0, "forward_min_rows": 200,
             "hgb": {"loss": "absolute_error", "max_iter": 200, "max_leaf_nodes": 31, "learning_rate": 0.1, "early_stopping": False}},
    "stage4": {"rf": {"n_estimators": 100, "max_leaf_nodes": 128, "min_samples_leaf": 5, "max_features": "sqrt"},
               "presel_quantiles": [0.005, 0.995], "presel_dR_quantile": 0.99, "weight_temper": 0.5},
    "calibration": {"hgb": {"loss": "absolute_error", "max_iter": 100, "max_leaf_nodes": 31, "learning_rate": 0.1, "early_stopping": False}},
    "std": {"v_eff_grid": [0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.22]},
    "psd": {"v_g_grid": [0.14, 0.15, 0.16, 0.17, 0.18, 0.19, 0.20, 0.21, 0.22], "gatti_floor": 0.001, "proton_recoil_excess_mev": 1.0,
            # packaged = v3: v_g by the IQR fit on this grid, Gatti shapes from the stage-4 subset, raw (not dark-subtracted) TTR.
            # The v5 variant: shape_source "psd_ref", dark_subtract True, grid 0.06-0.22, and subsets_per_class["psd_ref"] = [1500, 500, 0, 4000, 0].
            "shape_source": "stage4", "dark_subtract": False},
    "chunk_examples": 100,
    "bootstrap_resamples": 200,
}
TRUSTED = ["sklearn.ensemble._forest.RandomForestClassifier", "sklearn.tree._classes.DecisionTreeClassifier",
           "sklearn.ensemble._hist_gradient_boosting.gradient_boosting.HistGradientBoostingRegressor",
           "sklearn.ensemble._hist_gradient_boosting.binning._BinMapper",
           "sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor",
           "sklearn._loss.loss.AbsoluteError", "sklearn._loss.link.IdentityLink", "sklearn._loss.link.Interval",
           "sklearn.tree._tree.Tree", "numpy.dtype", "builtins.slice"]

# --------------------------------------------------------------------------------------- process pool plumbing
_G = _M = _TRUTH = None
_FILES = {}


_WITH_LABELS = False          # training reads labels (targets); evaluate/export never open a labels file


def _wf(path):
    if path not in _FILES:
        lab = path[:-3] + ".labels.h5"
        _FILES[path] = WaveformFile(path, lab if (_WITH_LABELS and os.path.exists(lab)) else None)
    return _FILES[path]


def preload(paths):
    """Load every file's index arrays in the parent BEFORE the pool forks, so workers share them copy-on-write
    (memory then does not grow with --procs); each worker re-opens only the HDF5 handles."""
    for p in paths:
        _wf(p)


def _init_worker():
    threadpool_limits(1)
    for W in _FILES.values():                       # never reuse an HDF5 handle opened before the fork
        W.reopen()


def _pool_map(fn, tasks, procs):
    import multiprocessing as mp
    if procs <= 1:
        _init_worker()
        return [fn(t) for t in tasks]
    with mp.get_context("fork").Pool(procs, initializer=_init_worker) as p:
        return p.map(fn, tasks, chunksize=1)


def _chunks(items, n):
    return [items[i:i + n] for i in range(0, len(items), n)]


def _truth_e(path, e):
    W = _wf(path)
    return {k: (v[e].decode() if isinstance(v[e], bytes) else v[e]) for k, v in W.truth.items()}


# --------------------------------------------------------------------------------------- per-example work
def _task_stage1(task):
    """Stage-1 training rows of a chunk: (X, y, rows per example), with at most rows_per_example random rows each."""
    import layoutb as lb
    seed, items = task
    X_, y_, n_ = [], [], []
    for path, e in items:
        res = _wf(path).example(e, with_truth=True)
        X, y, _, _, _, _ = oc.rows(res, _G, with_truth=True)
        k = min(len(X), HP["stage1"]["rows_per_example"])
        n_.append(k)
        if k == 0:
            continue
        sel = np.sort(np.random.default_rng([seed, 1, _file_no(path), e]).choice(len(X), k, replace=False))
        X_.append(X[sel]); y_.append(y[sel])
    if not X_:
        return np.zeros((0, oc.NWAVE + lb.N_EXTRA), np.float32), np.zeros(0, np.int8), np.array(n_, np.int64)
    return np.vstack(X_), np.concatenate(y_), np.array(n_, np.int64)


def _file_no(path):
    return int(os.path.basename(path).split("_")[1][:3])


def _task_stage2_dist(task):
    seed, items = task
    F2, C2, DF, DY, DW, DH, TT, TR, TW, TY, TQ, VT, VR, VW = [], [], [], [], [], [], [], [], [], [], [], [], [], []
    for path, e, hold in items:
        res = _wf(path).example(e, with_truth=True)
        T = _truth_e(path, e)
        X, y, wn, pmt, k_on, src = oc.rows(res, _G, with_truth=True)
        if len(X) == 0:
            continue
        keep = oc.forest_proba(_M["s1"], X)[:, 1] >= _M["p_cut"]
        q = oc.pulse_charge(X)
        wcls = oc.window_truth_classes(res, T)
        tle = oc.leading_edge_ns(X)
        vtx_ = np.array([T["prompt_x"], T["prompt_y"], T["prompt_z"]], float) / 1000.0
        cap_ = np.array([T["delayed_x"], T["delayed_y"], T["delayed_z"]], float) / 1000.0
        for w in range(len(res["win_start"])):
            if wcls[w] < 0:
                continue
            f2, _ = oc.window_s2_features(k_on, q, pmt, (wn == w) & keep, _G)
            F2.append(f2); C2.append(wcls[w])
            # conventional time PDF: first hits of ALL pulses vs the window's true source (overlap windows skipped)
            src_ = vtx_ if w == 0 else cap_
            if wcls[w] != 3 and np.all(np.isfinite(src_)) and (wn == w).sum() >= 20:
                mw = wn == w
                hp, ht, hq, ix = oc.first_hits(tle[mw], pmt[mw], q[mw], return_index=True)
                k = min(len(hp), 200)
                sel = np.sort(np.random.default_rng([seed, 3, _file_no(path), e, w]).choice(len(hp), k, replace=False))
                TT.append(ht[sel]); TR.append(np.linalg.norm(_G.P[hp[sel]] - src_, axis=1)); TW.append(np.full(k, len(TW), np.int64))
                TY.append(y[mw][ix[sel]].astype(bool)); TQ.append(hq[sel])
                # B1: real, Stage-1-kept pulses (all, not first hits) for the TOF group velocity
                rk = np.flatnonzero(mw & keep & (y == 1))
                if len(rk) >= 20:
                    k2 = min(len(rk), 300)
                    sel2 = np.sort(np.random.default_rng([seed, 4, _file_no(path), e, w]).choice(rk, k2, replace=False))
                    VT.append(tle[sel2]); VR.append(np.linalg.norm(_G.P[pmt[sel2]] - src_, axis=1)); VW.append(np.full(k2, len(VW), np.int64))
        # distance rows: truth-real pulses; target = distance from the pulse's source point to its PMT (m)
        vtx = np.array([T["prompt_x"], T["prompt_y"], T["prompt_z"]], float) / 1000.0
        cap = np.array([T["delayed_x"], T["delayed_y"], T["delayed_z"]], float) / 1000.0
        if not np.all(np.isfinite(cap)):
            cap = vtx
        real = np.flatnonzero(y == 1)
        if len(real) == 0:
            continue
        k = min(len(real), HP["dist"]["rows_per_example"])
        sel = np.sort(np.random.default_rng([seed, 2, _file_no(path), e]).choice(real, k, replace=False))
        df = oc.dist_features(X, wn, q)[sel]
        srcpos = np.where((src[sel] == 2)[:, None], cap[None, :], vtx[None, :])
        DF.append(df); DY.append(np.linalg.norm(_G.P[pmt[sel]] - srcpos, axis=1).astype(np.float32))
        DW.append(wn[sel].astype(np.int8)); DH.append(np.full(k, hold, bool))
    cat = lambda L, shape, dt: np.concatenate(L).astype(dt) if L else np.zeros(shape, dt)
    return (np.vstack(F2) if F2 else np.zeros((0, len(oc.MR_EDGES) - 1 + 4 + 2 + oc.N_PATCH + 2), np.float32), np.asarray(C2, np.int64),
            np.vstack(DF) if DF else np.zeros((0, oc.NWAVE + 7), np.float32), cat(DY, 0, np.float32), cat(DW, 0, np.int8), cat(DH, 0, bool),
            cat(TT, 0, np.float64), cat(TR, 0, np.float64), cat(TW, 0, np.int64), cat(TY, 0, bool), cat(TQ, 0, np.float64),
            cat(VT, 0, np.float64), cat(VR, 0, np.float64), cat(VW, 0, np.int64))


def _task_chain(task):
    items = task
    out = [[] for _ in range(6)]
    for path, e in items:
        for L, v in zip(out, oc.chain_example(_wf(path).example(e), _G, _M)):
            L.append(v)
    return tuple(np.array(L) for L in out)


# --------------------------------------------------------------------------------------- helpers
def group_files(data_dir, group):
    files = sorted(glob.glob(os.path.join(glob.escape(data_dir), f"{group}_[0-9][0-9][0-9].h5")))
    if not files:
        raise SystemExit(f"no {group}_NNN.h5 files in {data_dir}")
    return files


def pick_subsets(files, seed):
    """Disjoint, seeded example subsets per stage, drawn per dataset class from all train files."""
    inv = []
    for path in files:
        with h5py.File(path[:-3] + ".labels.h5", "r") as L:
            cls = L["truth/cls"][()]
        inv += [(path, e, int(c)) for e, c in enumerate(cls)]
    rng = np.random.default_rng([seed, 0])
    by_cls = {c: [i for i, t in enumerate(inv) if t[2] == c] for c in range(5)}
    order = {c: rng.permutation(v) for c, v in by_cls.items()}
    used = {c: 0 for c in range(5)}
    out = {}
    for stage in [k for k in ("stage1", "stage2_dist", "stage4_calibration", "psd_ref") if k in HP["subsets_per_class"]]:
        sel = []
        for c in range(5):
            n = min(HP["subsets_per_class"][stage][c], len(order[c]) - used[c])
            sel += [inv[i] for i in order[c][used[c]:used[c] + n]]
            used[c] += n
        out[stage] = sorted(sel, key=lambda t: (t[0], t[1]))
    return out


def forward_model(pred, true, wn, hold):
    """Per-window-type forward model: g(d) = median predicted distance and sigma(d) = half the 16-84 % spread of the
    prediction, in true-distance bins, from held-out rows (the regressor shrinks large distances toward the mean)."""
    out = {}
    b = HP["dist"]["forward_bin_m"]
    for key, m in (("0", hold & (wn == 0)), ("1", hold & (wn >= 1))):
        c, g, s = [], [], []
        for lo in np.arange(0, np.ceil(true[m].max() if m.any() else 1), b):
            mm = m & (true >= lo) & (true < lo + b)
            if mm.sum() >= HP["dist"]["forward_min_rows"]:
                c.append(lo + b / 2); g.append(float(np.median(pred[mm])))
                q16, q84 = np.quantile(pred[mm], [0.16, 0.84]); s.append(float(max(0.5 * (q84 - q16), 0.05)))
        out[key] = (np.array(c), np.array(g), np.array(s))
    return out


def time_pdf(TT, TR, TW, TY, TQ):
    """Conventional time-residual PDF from train truth. v_eff: the grid value with the narrowest residual distribution
    of the REAL-light first hits (IQR after removing each window's real-hit median). PDF: 2 ns histogram on
    [-200, 1000] ns of ALL first hits (real + dark, so the flat dark floor has its true size), centred the same way,
    plus half a count per bin, as log density."""
    bounds = np.flatnonzero(np.diff(TW)) + 1                          # windows are stored contiguously
    best = None
    for v in HP["std"]["v_eff_grid"]:
        r = TT - TR / v
        meds = np.array([np.median(g[y]) if y.sum() >= 5 else np.nan for g, y in zip(np.split(r, bounds), np.split(TY, bounds))])
        med = np.repeat(meds, np.diff(np.concatenate(([0], bounds, [len(r)]))))
        ok = np.isfinite(med)
        rr = r - med
        iqr = float(np.subtract(*np.quantile(rr[ok & TY], [0.75, 0.25])))
        if best is None or iqr < best[0]:
            best = (iqr, v, rr[ok], TQ[ok])
    edges = np.arange(-200.0, 1000.0 + 2.0, 2.0)
    qc = np.clip(np.searchsorted(oc.STD_Q_EDGES, best[3], side="right") - 1, 0, len(oc.STD_Q_EDGES) - 2)
    logf = []
    for c in range(len(oc.STD_Q_EDGES) - 1):                          # one PDF per PMT-charge class
        h, _ = np.histogram(best[2][qc == c], bins=edges)
        f = (h + 0.5) / ((h + 0.5).sum() * 2.0)
        logf.append(np.log(f))
    return {"x": 0.5 * (edges[1:] + edges[:-1]), "logf": np.array(logf), "v_eff": float(best[1]), "mode": 0.0, "median": 0.0,
            "iqr_ns": best[0], "hits_per_class": np.bincount(qc, minlength=len(oc.STD_Q_EDGES) - 1).tolist()}


def group_velocity(VT, VR, VW):
    """B1: TOF velocity for ALL real pulses: the grid value giving the narrowest t - r/v distribution (IQR after removing
    each window's median), from train truth source positions."""
    bounds = np.flatnonzero(np.diff(VW)) + 1
    best = None
    for v in HP["psd"]["v_g_grid"]:
        rr = np.concatenate([g - np.median(g) for g in np.split(VT - VR / v, bounds)])
        iqr = float(np.subtract(*np.quantile(rr, [0.75, 0.25])))
        if best is None or iqr < best[0]:
            best = (iqr, v)
    return float(best[1])


def radial_table(fit, true, edges):
    """Binned median correction true - fit as a function of the fitted coordinate (the classical bias map)."""
    k = np.clip(np.searchsorted(edges, fit, side="right") - 1, 0, len(edges) - 2)
    corr = np.array([np.median(true[k == i] - fit[k == i]) if (k == i).sum() >= 30 else 0.0 for i in range(len(edges) - 1)])
    return np.vstack([0.5 * (edges[1:] + edges[:-1]), corr])


def std_calibrated(SV, tabs, base=0):
    """Apply the conventional radial (rho) and axial (z) bias maps to the prompt and capture fits (columns of STD_NAMES;
    base = 0 for the all-hit fit, len(STD_NAMES)//2 for the Stage-1-cleaned variant)."""
    out = []
    for off in (base + 3, base + 6):
        v = SV[:, off:off + 3]
        rho = np.hypot(v[:, 0], v[:, 1]); phi = np.arctan2(v[:, 1], v[:, 0])
        rho2 = np.clip(rho + np.interp(rho, tabs["rho"][0], tabs["rho"][1]), 0, oc.R_MAX)
        z2 = np.clip(v[:, 2] + np.interp(v[:, 2], tabs["z"][0], tabs["z"][1]), -oc.Z_MAX, oc.Z_MAX)
        out.append(np.column_stack([rho2 * np.cos(phi), rho2 * np.sin(phi), z2]))
    return out


def save_model(M, path):
    import skops.io as sio
    blob = {"s1": M["s1"], "p_cut": float(M["p_cut"]), "s2": M["s2"], "dist": M["dist"], "s4": M["s4"],
            "cal_r": M["cal_r"], "cal_z": M["cal_z"],
            "presel": np.asarray(M["presel"], float), "v_g": float(M["v_g"]), "psd_dark_sub": bool(M.get("psd_dark_sub", False)), "gatti_w": np.asarray(M["gatti_w"]),
            "gatti_w_std": np.asarray(M["gatti_w_std"]), "gatti_w_std_clean": np.asarray(M["gatti_w_std_clean"]), "fwd0": np.vstack(M["fwd0"]), "fwd1": np.vstack(M["fwd1"]), "hp_json": json.dumps(HP), "format": "obd17kt-baseline-v1",
            "tpdf_x": M["tpdf"]["x"], "tpdf_logf": M["tpdf"]["logf"], "tpdf_v_eff": float(M["tpdf"]["v_eff"]),
            "std_rho": M["std_tabs"]["rho"], "std_z": M["std_tabs"]["z"],
            "std_clean_rho": M["std_tabs_clean"]["rho"], "std_clean_z": M["std_tabs_clean"]["z"]}
    sio.dump(blob, path, compression=8, compresslevel=9)


def load_model(path):
    import skops.io as sio
    untrusted = sio.get_untrusted_types(file=path)
    bad = [t for t in untrusted if t not in TRUSTED]
    if bad:
        raise SystemExit(f"refusing to load {path}: unexpected types {bad}")
    b = sio.load(path, trusted=untrusted)
    M = {k: b[k] for k in ("s1", "p_cut", "s2", "dist", "s4", "cal_r", "cal_z")}
    M["presel"] = np.asarray(b["presel"], float)
    M["v_g"] = float(b["v_g"])
    if "psd_dark_sub" in b:
        M["psd_dark_sub"] = bool(b["psd_dark_sub"])
    else:
        M["psd_dark_sub"] = False
        print("load_model: blob has no psd_dark_sub key (model trained before 2026-11-14 18:00) -> raw TTR/Gatti (False)", flush=True)
    # consistency guard (review 2026-11-14): the blob's PSD settings must match what inference will compute
    hp_blob = json.loads(str(b["hp_json"])).get("psd", {})
    if "dark_subtract" in hp_blob and bool(hp_blob["dark_subtract"]) != M["psd_dark_sub"]:
        raise SystemExit(f"model {path}: hp psd.dark_subtract={hp_blob['dark_subtract']} but blob psd_dark_sub={M['psd_dark_sub']}")
    for k in ("gatti_w", "gatti_w_std", "gatti_w_std_clean"):
        if np.asarray(b[k]).shape != (oc.N_PSD,):
            raise SystemExit(f"model {path}: {k} has shape {np.asarray(b[k]).shape}, inference expects ({oc.N_PSD},)")
    if not (0.0 < float(b["v_g"]) < 0.4):
        raise SystemExit(f"model {path}: implausible v_g {float(b['v_g'])}")
    n4 = len(oc.S4_NAMES) + len(oc.S4X_EXTRA)
    if getattr(b["s4"], "n_features_in_", n4) != n4:
        raise SystemExit(f"model {path}: Stage-4 expects {b['s4'].n_features_in_} features, inference builds {n4}")
    print(f"load_model: psd shape_source={hp_blob.get('shape_source', 'n/a')} dark_subtract={M['psd_dark_sub']} v_g={float(b['v_g']):g}", flush=True)
    for k in ("gatti_w", "gatti_w_std", "gatti_w_std_clean"):
        M[k] = np.asarray(b[k])
    M["fwd0"], M["fwd1"] = tuple(np.asarray(b["fwd0"])), tuple(np.asarray(b["fwd1"]))
    M["tpdf"] = {"x": np.asarray(b["tpdf_x"]), "logf": np.asarray(b["tpdf_logf"]), "v_eff": float(b["tpdf_v_eff"]), "mode": 0.0, "median": 0.0}
    M["std_tabs"] = {"rho": np.asarray(b["std_rho"]), "z": np.asarray(b["std_z"])}
    M["std_tabs_clean"] = {"rho": np.asarray(b["std_clean_rho"]), "z": np.asarray(b["std_clean_z"])}
    for k in ("s1", "s2", "s4"):
        M[k].n_jobs = 1
    return M


def run_chain(files, procs):
    preload(files)
    items = []
    for path in files:
        items += [(path, e) for e in range(len(_wf(path)))]
    res = _pool_map(_task_chain, _chunks(items, HP["chunk_examples"]), procs)
    return (items,) + tuple(np.vstack([r[k] for r in res]) for k in range(6))


def preselect(F, cuts):
    """Physical preselection (user decision 2026-11-14): prompt light, delayed light (two-window candidates) and the
    prompt-capture distance inside windows that keep ~99 % of train geo-IBDs. Returns a boolean pass mask."""
    f = lambda k: F[:, oc.S4_NAMES.index(k)]
    two = f("n_windows") >= 2
    ok = (f("q_prompt") >= cuts[0]) & (f("q_prompt") <= cuts[1])
    ok &= ~two | ((f("q_delayed") >= cuts[2]) & (f("q_delayed") <= cuts[3]) & (f("dR_m") <= cuts[4]))
    return ok


def geo_score(M, F):
    """P(IBD) from Stage 4 for preselected candidates; a candidate failing the preselection gets P(IBD) - 1, i.e. below
    every passing candidate but still ordered (the metric needs a score for every id; Health rejects a constant score)."""
    p = np.zeros((len(F), 3)); p[:, M["s4"].classes_] = M["s4"].predict_proba(F)
    s = p[:, 0].copy()
    s[~preselect(F, M["presel"])] -= 1.0
    return s, p


def predictions(M, items, F, PF, CF, calibrate=True):
    s, p = geo_score(M, F)
    p[:, 0] = s
    pos = oc.apply_calibration(F, PF, CF, M["cal_r"], M["cal_z"]) if calibrate else PF
    out = {}
    for i, (path, e) in enumerate(items):
        v = [float(x) for x in pos[i]]
        out[f"{os.path.basename(path)[:-3]}:{e:06d}"] = [float(p[i, 0])] + v + v
    return out


def task_metrics(pred_path, preds, data_dir):
    """The task's declared metrics, computed by the task's own metric plugins (primary + secondary_metrics)."""
    from execute_tools.task_data_path import ScopeBuildRequest, bind_task_data_path
    from workflows.task_composition import compose_run_task_bindings
    comp = compose_run_task_bindings(os.path.abspath(TASK_YAML))
    dp = comp.task_data_path
    scope = dp.build_eval_scope(ScopeBuildRequest(round_kind="formal", selection_strategy="snapshot", portion=1.0))
    ids = dp.example_ids(scope, data_dir)
    missing = [i for i in ids if i not in preds]
    if missing:
        raise SystemExit(f"{len(missing)} evaluation examples have no prediction (e.g. {missing[:3]})")
    out = {}
    with bind_task_data_path(dp):
        for m in [comp.metric, *comp.secondary_metrics]:
            r = m.evaluate({0: pred_path}, evaluation_payload=preds, task_scope=scope, data_dir=data_dir)
            if getattr(r, "scalar", None) is None or not np.isfinite(r.scalar):
                raise SystemExit(f"metric {m.spec.id} is not scoreable: {r}")
            out[m.spec.id] = float(r.scalar)
        truth = dp.truth_table(scope, data_dir)
    return out, truth


def bootstrap(preds, truth, n_boot, seed):
    """68 % / 95 % intervals of every metric: examples resampled with replacement within each dataset class, each
    resample scored by the task plugin's own score_components (the same function the metric classes call)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_obd_metrics_bs", os.path.join(HERE, "..", "task", "plugins", "_obd_metrics.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    T = {k: np.asarray(truth[k]) for k in ("ids", "cls", "weight", "prompt_m", "capture_m", "split")}
    rng = np.random.default_rng([seed, 99])
    draws = {}
    for _ in range(n_boot):
        idx = np.concatenate([rng.choice(np.flatnonzero(T["cls"] == c), (T["cls"] == c).sum(), replace=True) for c in np.unique(T["cls"])])
        sub = {k: v[idx] for k, v in T.items()}
        sub["ids"] = list(sub["ids"])
        comp = mod.score_components(preds, sub)
        wedge = sub["split"] == "val_wedge"
        comp["obd_combined_val_wedge"] = mod.score_components(preds, sub, wedge)["obd_combined"] if wedge.any() else float("nan")
        for k, v in comp.items():
            draws.setdefault(k, []).append(v)
    return {k: {"q2.5": float(np.nanquantile(v, 0.025)), "q16": float(np.nanquantile(v, 0.16)), "median": float(np.nanmedian(v)),
                "q84": float(np.nanquantile(v, 0.84)), "q97.5": float(np.nanquantile(v, 0.975))} for k, v in draws.items()} | {"n_boot": n_boot}


def evaluate(M, data_dir, out_dir, procs, log):
    t0 = time.perf_counter()
    items, F4, PF, CF, SV, PX, SH = run_chain(group_files(data_dir, "val"), procs)
    F = oc.stage4_matrix(F4, PX, M)
    log["evaluate_chain_s"] = time.perf_counter() - t0
    preds = predictions(M, items, F, PF, CF)
    pred_path = os.path.join(out_dir, "predictions.json")
    with open(pred_path, "w") as f:
        json.dump(preds, f)
    met, truth = task_metrics(pred_path, preds, data_dir)
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(met, f, indent=1, sort_keys=True)
    with open(os.path.join(out_dir, "metrics_bootstrap.json"), "w") as f:
        json.dump(bootstrap(preds, truth, HP["bootstrap_resamples"], 20261114), f, indent=1, sort_keys=True)
    log["evaluate_s"] = time.perf_counter() - t0
    log["metrics"] = met
    # guard: the calibration acts on positions only, so the selection metrics must not change without it
    raw = predictions(M, items, F, PF, CF, calibrate=False)
    log["selection_unchanged_without_calibration"] = all(raw[k][0] == preds[k][0] for k in preds)
    write_export(os.path.join(out_dir, "chain_outputs.npz"), M, items, F, PF, CF, SV, SH)
    return met


def write_export(path, M, items, F, PF, CF, SV, SH):
    """Per-example chain outputs, NO truth: ML Stage-4 features and score, ML positions (raw and calibrated), and the
    conventional analysis (dark-subtracted energies, fitted-t0 dt, time-likelihood fits raw and bias-corrected, status)."""
    s_, p = geo_score(M, F)
    sp_cal, sc_cal = std_calibrated(SV, M["std_tabs"])
    cp_cal, cc_cal = std_calibrated(SV, M["std_tabs_clean"], len(oc.STD_NAMES) // 2)
    np.savez_compressed(path, ids=np.array([f"{os.path.basename(q)[:-3]}:{e:06d}" for q, e in items]),
                        s4_features=F, s4_names=np.array(oc.S4_NAMES + oc.S4X_EXTRA), ml_score=s_, ml_preselected=preselect(F, M["presel"]), ml_p_alphan=p[:, 1], ml_p_accidental=p[:, 2],
                        ml_prompt_raw=PF, ml_capture_raw=CF, ml_position_calibrated=oc.apply_calibration(F, PF, CF, M["cal_r"], M["cal_z"]),
                        std=SV, std_names=np.array(oc.STD_NAMES), std_prompt_calibrated=sp_cal, std_capture_calibrated=sc_cal,
                        clean_prompt_calibrated=cp_cal, clean_capture_calibrated=cc_cal,
                        std_ttr_prompt=SH[:, 0], clean_ttr_prompt=SH[:, 1],
                        std_gatti_prompt=np.nan_to_num(SH[:, 2:2 + oc.N_PSD]) @ M["gatti_w_std"],
                        clean_gatti_prompt=np.nan_to_num(SH[:, 2 + oc.N_PSD:]) @ M["gatti_w_std_clean"],
                        std_v_eff_m_per_ns=float(M["tpdf"]["v_eff"]), nominal_pe_per_mev=400.0,
                        note=np.array("std energies: PE in residual window -50..250 ns at the fitted vertex minus pre-trigger dark density; "
                                      "dt_ns: fitted t0 difference; *_ok/nll/n_pmt: fit status; MeV scale nominal (LY 10000/MeV -> ~400 PE/MeV)"))


def export(M, data_dir, patterns, out_dir, procs):
    """Run the chain on every file matching the patterns and write <stem>.chain.npz per file (for the comparison)."""
    files = sorted({f for pat in patterns for f in glob.glob(os.path.join(glob.escape(data_dir), pat)) if not f.endswith(".labels.h5")})
    if not files:
        raise SystemExit(f"no files match {patterns} in {data_dir}")
    for f in files:
        t0 = time.perf_counter()
        items, F4, PF, CF, SV, PX, SH = run_chain([f], procs)
        out = os.path.join(out_dir, os.path.basename(f)[:-3] + ".chain.npz")
        write_export(out, M, items, oc.stage4_matrix(F4, PX, M), PF, CF, SV, SH)
        print(json.dumps({"file": f, "examples": len(items), "s": round(time.perf_counter() - t0, 1), "out": out}), flush=True)


# --------------------------------------------------------------------------------------- train
def train(data_dir, seed, out_dir, procs, log):
    global _G, _M, _WITH_LABELS
    _WITH_LABELS = True
    from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestClassifier
    t0 = time.perf_counter()
    _G = oc.Geometry(os.path.join(data_dir, "pmt_geometry.h5"))
    files = group_files(data_dir, "train")
    preload(files)
    sub = pick_subsets(files, seed)
    log["subset_sizes"] = {k: len(v) for k, v in sub.items()}
    M = {}

    # Stage 1: hit cleaner (rows from the stage1 subset; p_cut from its held-out part)
    rng = np.random.default_rng([seed, 10])
    s1 = sub["stage1"]; hold = rng.random(len(s1)) < HP["stage1"]["holdout_fraction"]
    tasks = [(seed, c) for c in _chunks([(p, e) for (p, e, _) in s1], HP["chunk_examples"])]
    parts = _pool_map(_task_stage1, tasks, procs)
    X1 = np.vstack([r[0] for r in parts]); y1 = np.concatenate([r[1] for r in parts])
    ex_of_row = np.repeat(np.arange(len(s1)), np.concatenate([r[2] for r in parts]))
    tr_rows, ho_rows = ~hold[ex_of_row], hold[ex_of_row]
    rf1 = RandomForestClassifier(**HP["stage1"]["rf"], n_jobs=procs, random_state=seed)
    rf1.fit(X1[tr_rows], y1[tr_rows])
    rf1.n_jobs = 1
    p_ho = oc.forest_proba(rf1, X1[ho_rows])[:, 1]
    M["s1"] = rf1
    M["p_cut"] = float(np.quantile(p_ho[y1[ho_rows] == 1], 1 - HP["stage1"]["keep_real_fraction"]))
    log["stage1"] = {"rows_train": int(tr_rows.sum()), "rows_holdout": int(ho_rows.sum()), "p_cut": M["p_cut"],
                     "noise_removed_holdout": float((p_ho[y1[ho_rows] == 0] < M["p_cut"]).mean()), "t_s": time.perf_counter() - t0}
    print("stage1", json.dumps(log["stage1"]), flush=True)

    # Stage 2 + distance regressor (stage2_dist subset)
    _M = M
    s2 = sub["stage2_dist"]; hold2 = np.random.default_rng([seed, 20]).random(len(s2)) < HP["dist"]["holdout_fraction"]
    tasks = [(seed, c) for c in _chunks([(p, e, bool(h)) for (p, e, _), h in zip(s2, hold2)], HP["chunk_examples"])]
    parts = _pool_map(_task_stage2_dist, tasks, procs)
    F2 = np.vstack([r[0] for r in parts]); C2 = np.concatenate([r[1] for r in parts])
    DF = np.vstack([r[2] for r in parts]); DY = np.concatenate([r[3] for r in parts])
    DW = np.concatenate([r[4] for r in parts]); DH = np.concatenate([r[5] for r in parts])
    TT = np.concatenate([r[6] for r in parts]); TR = np.concatenate([r[7] for r in parts])
    TW = np.concatenate([r[8] + o for r, o in zip(parts, np.cumsum([0] + [int(r[8].max()) + 1 if len(r[8]) else 0 for r in parts[:-1]]))])
    TY = np.concatenate([r[9] for r in parts]); TQ = np.concatenate([r[10] for r in parts])
    M["tpdf"] = time_pdf(TT, TR, TW, TY, TQ)
    VT = np.concatenate([r[11] for r in parts]); VR = np.concatenate([r[12] for r in parts])
    VW = np.concatenate([r[13] + o for r, o in zip(parts, np.cumsum([0] + [int(r[13].max()) + 1 if len(r[13]) else 0 for r in parts[:-1]]))])
    M["v_g"] = group_velocity(VT, VR, VW)
    log["v_g_m_per_ns"] = M["v_g"]
    log["std_time_pdf"] = {"v_eff_m_per_ns": M["tpdf"]["v_eff"], "residual_iqr_ns": M["tpdf"]["iqr_ns"], "hits": int(len(TT)),
                           "hits_per_charge_class": M["tpdf"]["hits_per_class"]}
    rf2 = RandomForestClassifier(**HP["stage2"]["rf"], n_jobs=procs, random_state=seed)
    rf2.fit(F2, C2); rf2.n_jobs = 1
    M["s2"] = rf2
    with threadpool_limits(1):
        dist = HistGradientBoostingRegressor(**HP["dist"]["hgb"], random_state=seed).fit(DF[~DH], DY[~DH])
    M["dist"] = dist
    pr = dist.predict(DF[DH])
    fw = forward_model(pr, DY[DH], DW[DH], np.ones(DH.sum(), bool))
    M["fwd0"], M["fwd1"] = fw["0"], fw["1"]
    log["stage2"] = {"windows": int(len(C2)), "class_counts": np.bincount(C2, minlength=7).tolist()}
    log["dist"] = {"rows_train": int((~DH).sum()), "rows_holdout": int(DH.sum()), "median_abs_err_holdout_m": float(np.median(np.abs(pr - DY[DH]))),
                   "t_s": time.perf_counter() - t0}
    print("stage2/dist", json.dumps({**log["stage2"], **log["dist"]}), flush=True)

    # Stage 4 + position calibration (stage4_calibration subset): run the full chain with the models above
    _M = M
    M["want_std"] = True
    M["psd_dark_sub"] = bool(HP["psd"]["dark_subtract"])
    if HP["psd"]["shape_source"] == "psd_ref":
        # variant v5: v_g by PSD scan and Gatti shapes on the DISJOINT psd_ref subset
        # B1/B2 on the DISJOINT psd_ref subset (review notes): choose v_g by the train proton-recoil rejection at 95 % geo
        # (dark-subtracted tail-to-total), then build the Gatti reference shapes there; Stage 4 trains on its own subset.
        ref_items = [(p, e) for (p, e, _) in sub["psd_ref"]]
        rcls = np.array([c for (_, _, c) in sub["psd_ref"]])
        rtr = [_truth_e(p, e) for (p, e) in ref_items]
        exc = np.array([float(t["edep_a"]) - float(t["n_ke"]) - 4.78 if c == 3 else np.nan for t, c in zip(rtr, rcls)])
        v_iqr = M["v_g"]; scan = {}
        M["want_std"] = False
        for v in HP["psd"]["v_g_grid"]:
            M["v_g"] = v
            _, rF4, _, _, _, rPX, _ = _chain_items(ref_items, procs)
            ok_ = rF4[:, oc.S4_NAMES.index("npulse_prompt")] >= 10
            s_, p_ = np.isin(rcls, [0, 1]) & ok_, (rcls == 3) & (exc < HP["psd"]["proton_recoil_excess_mev"]) & ok_
            thr = np.quantile(rPX[s_, 0], 0.95)
            scan[v] = float((rPX[p_, 0] > thr).mean())
        v_best = max(scan, key=lambda v: (scan[v], -abs(v - v_iqr)))
        M["v_g"] = v_best; M["want_std"] = True
        log["v_g_selection"] = {"iqr_optimal": v_iqr, "psd_optimal": v_best, "ttr_rejection_at_95pct_geo_by_v": {f"{k:g}": x for k, x in scan.items()}}
        print("v_g", json.dumps(log["v_g_selection"]), flush=True)
        _, rF4, _, _, _, rPX, rSH = _chain_items(ref_items, procs)
        np_ok = rF4[:, oc.S4_NAMES.index("npulse_prompt")] >= 10
        sig_ = np.isin(rcls, [0, 1]) & np_ok; pr_ = (rcls == 3) & (exc < HP["psd"]["proton_recoil_excess_mev"]) & np_ok
        hp_ = rPX[:, len(oc.PX_NAMES):len(oc.PX_NAMES) + oc.N_PSD]
        M["gatti_w"] = oc.gatti_weights(hp_[sig_].mean(0), hp_[pr_].mean(0), HP["psd"]["gatti_floor"])
        for key, off in (("gatti_w_std", 2), ("gatti_w_std_clean", 2 + oc.N_PSD)):
            H = rSH[:, off:off + oc.N_PSD]; ok_ = np.all(np.isfinite(H), axis=1)
            M[key] = oc.gatti_weights(H[sig_ & ok_].mean(0), H[pr_ & ok_].mean(0), HP["psd"]["gatti_floor"])
    s4 = sub["stage4_calibration"]
    items, F4, PF, CF, SV, PX, SH = _chain_items([(p, e) for (p, e, _) in s4], procs)
    cls = np.array([c for (_, _, c) in s4]); y4 = np.array([oc.CLASS4[c] for c in cls])
    # B2: Gatti reference shapes from train: geo-IBD prompts (r_e) vs (alpha,n) proton-recoil prompts (r_p; truth proxy
    # E_excess = edep_a - n_ke - 4.78 MeV below the cut = no 16O*/12C gamma branch). The same recipe on the conventional
    # fit's profiles gives the conventional reference its own Gatti weights (B7 fairness).
    tr_ = [_truth_e(p, e) for (p, e) in items]
    exc4 = np.array([float(t["edep_a"]) - float(t["n_ke"]) - 4.78 if c == 3 else np.nan for t, c in zip(tr_, cls)])
    ok4 = F4[:, oc.S4_NAMES.index("npulse_prompt")] >= 10
    sig4 = np.isin(cls, [0, 1]) & ok4; pr4 = (cls == 3) & (exc4 < HP["psd"]["proton_recoil_excess_mev"]) & ok4
    if HP["psd"]["shape_source"] == "stage4":
        # baseline v3 (the packaged model): Gatti shapes from the stage-4 training subset itself (in-sample; val/test
        # stay independent). Compared with v5 on validation, v3 scored higher (card).
        sig_, pr_ = sig4, pr4
        hp_ = PX[:, len(oc.PX_NAMES):len(oc.PX_NAMES) + oc.N_PSD]
        M["gatti_w"] = oc.gatti_weights(hp_[sig_].mean(0), hp_[pr_].mean(0), HP["psd"]["gatti_floor"])
        for key, off in (("gatti_w_std", 2), ("gatti_w_std_clean", 2 + oc.N_PSD)):
            H = SH[:, off:off + oc.N_PSD]; ok_ = np.all(np.isfinite(H), axis=1)
            M[key] = oc.gatti_weights(H[sig_ & ok_].mean(0), H[pr_ & ok_].mean(0), HP["psd"]["gatti_floor"])
    F = oc.stage4_matrix(F4, PX, M)
    gcol = len(oc.S4_NAMES) + len(oc.PX_NAMES); ep = F4[:, oc.S4_NAMES.index("q_prompt")]
    rej = {}
    for lo, hi in ((0, 600), (600, 900), (900, 1300), (1300, 1e9)):
        m_s, m_p = sig4 & (ep >= lo) & (ep < hi), pr4 & (ep >= lo) & (ep < hi)
        if m_s.sum() >= 50 and m_p.sum() >= 20:
            for nm_, col_ in (("ttr", PX[:, 0]), ("gatti", F[:, gcol])):
                thr = np.quantile(col_[m_s], 0.95)          # keep 95 % of geo (proton recoil has the larger tail)
                rej[f"{nm_}_qprompt_{lo:g}-{hi:g}"] = {"proton_recoil_rejected": float((col_[m_p] > thr).mean()), "n_geo": int(m_s.sum()), "n_pr": int(m_p.sum())}
    log["psd"] = {"v_g_m_per_ns": M["v_g"], "n_geo_ref": int(sig_.sum()), "n_proton_recoil_ref": int(pr_.sum()),
                  "ttr_median_geo": float(np.median(PX[sig4, 0])), "ttr_median_proton_recoil": float(np.median(PX[pr4, 0])),
                  "gatti_median_geo": float(np.median(F[sig4, gcol])), "gatti_median_proton_recoil": float(np.median(F[pr4, gcol])),
                  "rejection_at_95pct_geo": rej}
    print("psd", json.dumps(log["psd"]), flush=True)
    wyr = np.array([_truth_e(p, e)["weight_per_year"] for (p, e) in items], float)
    # physical preselection windows from train geo-IBDs (quantiles keep ~99 % of the signal)
    geo = np.isin(cls, [0, 1]); fcol = lambda k: F[:, oc.S4_NAMES.index(k)]
    two = geo & (fcol("n_windows") >= 2)
    qa, qb = HP["stage4"]["presel_quantiles"]
    M["presel"] = np.array([np.quantile(fcol("q_prompt")[geo], qa), np.quantile(fcol("q_prompt")[geo], qb),
                            np.quantile(fcol("q_delayed")[two], qa), np.quantile(fcol("q_delayed")[two], qb),
                            np.quantile(fcol("dR_m")[two], HP["stage4"]["presel_dR_quantile"])])
    ps = preselect(F, M["presel"])
    # weights: physical yearly weights within each class, tempered (w^alpha), each class then normalised to equal total
    cw = np.zeros(len(y4)); ess = {}
    for c in range(3):
        m = ps & (y4 == c)
        w = wyr[m] ** HP["stage4"]["weight_temper"]
        cw[m] = w / max(w.sum(), 1e-300) * ps.sum() / 3.0
        ess[c] = float(w.sum() ** 2 / max((w ** 2).sum(), 1e-300)) if m.any() else 0.0
    rf4 = RandomForestClassifier(**HP["stage4"]["rf"], n_jobs=procs, random_state=seed)
    rf4.fit(F[ps], y4[ps], sample_weight=cw[ps]); rf4.n_jobs = 1
    M["s4"] = rf4
    log["stage4_preselection"] = {"cuts": M["presel"].tolist(), "pass_fraction_by_class": {int(c): float(ps[cls == c].mean()) for c in np.unique(cls)},
                                  "effective_sample_size": ess, "n_by_class_after": np.bincount(y4[ps], minlength=3).tolist()}
    print("stage4 preselection", json.dumps(log["stage4_preselection"]), flush=True)
    ibd = y4 == 0
    vt = np.array([[_truth_e(p, e)[f"prompt_{k}"] for k in "xyz"] for (p, e) in items], float) / 1000.0
    C = oc.calib_features(F, PF, CF)
    with threadpool_limits(1):
        M["cal_r"] = HistGradientBoostingRegressor(**HP["calibration"]["hgb"], random_state=seed).fit(
            C[ibd], np.hypot(vt[ibd, 0], vt[ibd, 1]) - np.hypot(PF[ibd, 0], PF[ibd, 1]))
        M["cal_z"] = HistGradientBoostingRegressor(**HP["calibration"]["hgb"], random_state=seed).fit(C[ibd], vt[ibd, 2] - PF[ibd, 2])
    ok = ibd & (SV[:, oc.STD_NAMES.index("prompt_ok")] > 0)
    sp_ = SV[:, 3:6]
    M["std_tabs"] = {"rho": radial_table(np.hypot(sp_[ok, 0], sp_[ok, 1]), np.hypot(vt[ok, 0], vt[ok, 1]), np.linspace(0, oc.R_MAX, 25)),
                     "z": radial_table(sp_[ok, 2], vt[ok, 2], np.linspace(-oc.Z_MAX, oc.Z_MAX, 45))}
    hb = len(oc.STD_NAMES) // 2
    okc = ibd & (SV[:, hb + oc.STD_NAMES.index("prompt_ok")] > 0); cp_ = SV[:, hb + 3:hb + 6]
    M["std_tabs_clean"] = {"rho": radial_table(np.hypot(cp_[okc, 0], cp_[okc, 1]), np.hypot(vt[okc, 0], vt[okc, 1]), np.linspace(0, oc.R_MAX, 25)),
                           "z": radial_table(cp_[okc, 2], vt[okc, 2], np.linspace(-oc.Z_MAX, oc.Z_MAX, 45))}
    log["stage4"] = {"examples": int(len(y4)), "class_counts": np.bincount(y4, minlength=3).tolist(), "t_s": time.perf_counter() - t0}
    print("stage4", json.dumps(log["stage4"]), flush=True)
    M["want_std"] = False
    path = os.path.join(out_dir, "final_model.skops")
    save_model(M, path)
    log["model_bytes"] = os.path.getsize(path)
    _WITH_LABELS = False
    for W in _FILES.values():
        W.close()
    _FILES.clear()
    log["train_s"] = time.perf_counter() - t0
    return path


def _chain_items(items, procs):
    res = _pool_map(_task_chain, _chunks(items, HP["chunk_examples"]), procs)
    return (items,) + tuple(np.vstack([r[k] for r in res]) for k in range(6))


def main():
    global _G, _M
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    t = sp.add_parser("train"); t.add_argument("--data_dir", required=True); t.add_argument("--seed", type=int, required=True)
    t.add_argument("--output_dir", required=True); t.add_argument("--init_model")
    e = sp.add_parser("evaluate"); e.add_argument("--data_dir", required=True); e.add_argument("--model", required=True)
    e.add_argument("--output_dir", required=True)
    x = sp.add_parser("export", help="run the chain on chosen files and write per-file npz (comparison with the conventional analysis)")
    x.add_argument("--data_dir", required=True); x.add_argument("--model", required=True); x.add_argument("--output_dir", required=True)
    x.add_argument("--files", nargs="+", required=True, help="glob patterns inside data_dir, e.g. 'val_*.h5'")
    for p in (t, e, x):
        p.add_argument("--procs", type=int, default=len(os.sched_getaffinity(0)))
    a = ap.parse_args()
    os.makedirs(a.output_dir, exist_ok=True)
    data_dir = os.path.abspath(a.data_dir)
    log = {"cmd": a.cmd, "procs": a.procs, "hp": HP}
    t0 = time.perf_counter()
    if a.cmd == "train":
        path = train(data_dir, a.seed, a.output_dir, a.procs, log)
        _M = load_model(path)                       # evaluate exactly what was saved
    else:
        _G = oc.Geometry(os.path.join(data_dir, "pmt_geometry.h5"))
        _M = load_model(a.model)
    if a.cmd == "export":
        _M["want_std"] = True
        export(_M, data_dir, a.files, a.output_dir, a.procs)
        return
    if _G is None:
        _G = oc.Geometry(os.path.join(data_dir, "pmt_geometry.h5"))
    met = evaluate(_M, data_dir, a.output_dir, a.procs, log)
    log["total_s"] = time.perf_counter() - t0
    with open(os.path.join(a.output_dir, f"{a.cmd}_log.json"), "w") as f:
        json.dump(log, f, indent=1)
    print(json.dumps(met, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
