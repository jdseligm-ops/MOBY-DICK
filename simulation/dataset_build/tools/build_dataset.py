#!/usr/bin/env python3
"""Build the hackathon dataset: digitised PMT waveforms of IBD, (alpha,n) and accidental examples, with truth and weights.

One example = everything the detector records from the first trigger to +50 us: one or more 1.2 us readout windows
of zero-suppressed 4 ns waveforms (digitize.py). It is digitised from photoelectrons, with dark noise and its own
per-example seed, so noise is continuous across the windows of one example.

Modes:
  scan         singles chunks -> for each simulated decay: does it trigger alone? plus vertex and split (flags npz)
  events       IBD / (alpha,n) chunk -> one example per event (shard .h5 + truth)
  accidentals  flags + singles chunks -> importance-sampled pairs: single A at t=0, single B at dt ~ U(0, 50 us),
               overlaid at the photoelectron level and digitised together (shard .h5 + truth)
  merge        shards -> final per-split files; computes the yearly weight of every example

Classes: 0 geoU, 1 geoTh, 2 reactor (IBD; reported separately in the score), 3 alphan, 4 accidental.
Splits (train_stage1.split_of): phi wedges 0-45 (val_wedge) and 180-225 (test_wedge) by the prompt vertex;
  elsewhere chunk seed % 10: 0-7 train, 8 val_random, 9 test_random. Singles are split by their OWN seed and vertex
  BEFORE pairing, and pairs are formed only within one split, so no simulated decay appears in two splits.
Weights (events per year represented by each example, per split; rates.py):
  IBD and (alpha,n): rate / (number of simulated events of that class in the split)
  accidental (i,j):  N_ij = R_i R_j T yr, with R = activity x f_trig (from scan). Pairs are drawn with probability
                     q = alpha * [d_true < 3 m] / C_ij + (1 - alpha) / (n_i n_j) instead of p = 1 / (n_i n_j), so the
                     weight is N_ij * (p / q) / M_ij (M_ij = number of pairs drawn for (i,j) in the split).
Truth (never an input): class, weight, prompt/delayed positions (IBD vertex / capture point; (alpha,n) vertex /
  capture point; singles A / B vertices), true dt, n_target, overlap, energies, source ids, and the real PEs per
  window (pmt, window, time, source label 1/2) for hit-level training. Dark PEs are everything else.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np

import digitize as dg
import rates
from train_stage1 import split_of

T_PAIR_NS = 50_000.0
CLASS_OF = {"geoU": 0, "geoTh": 1, "reactor": 2, "alphan": 3}
CLASS_NAMES = ["geoU", "geoTh", "reactor", "alphan", "accidental"]
CLOSE_M = 3.0
MID_M = 6.0
ALPHA_CLOSE = 0.35         # sampling mixture: 35 % uniform over d < 3 m pairs, 35 % uniform over 3-6 m pairs, 30 % uniform over all
ALPHA_MID = 0.35           # (user: 50/50 close/uniform; 3-6 m mode added on review 2026-11-13: the shell a dR selection leaks)
STRAT_EDGES = np.array([0.0, 1.5, 3.0, 4.5, 6.0, 9.0, 12.0, 20.0, 1e9])   # m, separation strata for the split-region correction
PROMPT_NHIT_MIN = 246     # candidate condition (user decisions 2026-11-13): PMTs with a pulse onset in [-20, +80) ns of
                          # window 0's trigger. v3 value for the gel/fixed-optics detector; see PROMPT_RULE.
PROMPT_LO, PROMPT_HI = -5, 20   # samples relative to the trigger sample
NEV_PER_CHUNK = 200             # generated events per simulation chunk (NEV in jobs/sim_ibd_array.sbatch)
PROMPT_RULE = ("Lowest threshold above every Po-210 alpha in the tuning sample (user decision 2026-11-13, gel detector): "
               "2,000 Po-210 decays (po210_ls_gel_b52 chunks 0-9) have prompt hits p99.9 238 and max 245, so the cut is 246. "
               "geo-U IBD (2,000, geoU_gel_b41 chunks 0-9) p0.5 225, p1 234; 97.9 % pass. (alpha,n) (999): 84.4 % pass. "
               "The leakage on the full Po-210 sample is measured by the scan (f_prompt) and weighted exactly. "
               "v2 used 180 for the old air/optics detector.")


def phi_deg(x, y):
    return float(np.degrees(np.arctan2(y, x)) % 360.0)


def prompt_nhit(res, cfg):
    """Data-level prompt size: number of PMTs with a pulse onset (up-crossing of the zero-suppression threshold) in
    [PROMPT_LO, PROMPT_HI) samples of window 0's trigger. Computable by anyone from the stored waveforms."""
    tr = int(res["win_trig"][0])
    pm = set()
    for s in np.flatnonzero(res["seg_win"] == 0):
        o, ln, st = int(res["seg_off"][s]), int(res["seg_len"][s]), int(res["seg_start"][s])
        ab = res["samples"][o:o + ln] > cfg.zs_threshold_adc
        up = np.flatnonzero(ab & ~np.concatenate(([False], ab[:-1]))) + st
        if np.any((up >= tr + PROMPT_LO) & (up < tr + PROMPT_HI)):
            pm.add(int(res["seg_pmt"][s]))
    return len(pm)


def digitize_example(srcs, n_pmt, cfg, rng):
    """srcs: list of (pmt, t_ns, label). Returns the digitised result restricted to windows within T_PAIR_NS of the first."""
    pm = np.concatenate([s[0] for s in srcs]); t = np.concatenate([s[1] for s in srcs]); lab = np.concatenate([s[2] for s in srcs])
    res = dg.digitize(pm, t, lab, n_pmt, cfg, rng)
    if res is None:
        return None
    keepw = np.flatnonzero(res["win_start"] * cfg.sample_ns <= T_PAIR_NS)
    nw = len(keepw)
    if nw < len(res["win_start"]):
        segm = np.isin(res["seg_win"], keepw)
        offs = res["seg_off"]
        samples = np.concatenate([res["samples"][offs[i]:offs[i + 1]] for i in np.flatnonzero(segm)]) if segm.any() else np.zeros(0, np.int16)
        lens = res["seg_len"][segm].astype(np.int64)
        res = {**res, "win_start": res["win_start"][:nw], "win_trig": res["win_trig"][:nw], "seg_pmt": res["seg_pmt"][segm],
               "seg_win": res["seg_win"][segm], "seg_start": res["seg_start"][segm], "seg_len": res["seg_len"][segm],
               "seg_off": np.concatenate(([0], np.cumsum(lens))), "samples": samples,
               "pe_win": np.where(res["pe_win"] < nw, res["pe_win"], -1)}
    return res


class Shard:
    """Accumulates examples and writes one HDF5 shard (waveforms) plus one truth npz."""

    def __init__(self):
        self.ex = {k: [] for k in ("n_win", "win_start", "win_trig", "seg_pmt", "seg_win", "seg_start", "seg_len", "samples")}
        self.pe = {k: [] for k in ("pmt", "win", "t", "label")}
        self.npe = []
        self.truth = []

    def add(self, res, truth):
        nw = len(res["win_start"])
        self.ex["n_win"].append(nw)
        for k in ("win_start", "win_trig", "seg_pmt", "seg_win", "seg_start", "seg_len", "samples"):
            self.ex[k].append(res[k])
        real = (res["pe_label"] > 0) & (res["pe_win"] >= 0)
        self.pe["pmt"].append(res["pe_pmt"][real]); self.pe["win"].append(res["pe_win"][real].astype(np.uint8))
        self.pe["t"].append(res["pe_t"][real]); self.pe["label"].append(res["pe_label"][real])
        self.npe.append(int(real.sum()))
        self.truth.append(truth)

    def write(self, path_h5, path_truth, meta):
        import h5py
        n = len(self.truth)
        cat = lambda k, dt: np.concatenate(self.ex[k]).astype(dt) if n else np.zeros(0, dt)
        nseg = np.array([len(x) for x in self.ex["seg_pmt"]], np.int64)
        with h5py.File(path_h5 + ".tmp", "w") as f:
            f.attrs["meta_json"] = json.dumps(meta)
            g = f.create_group("examples")
            g["win_off"] = np.concatenate(([0], np.cumsum(self.ex["n_win"]))).astype(np.int64)
            g["seg_off_by_example"] = np.concatenate(([0], np.cumsum(nseg))).astype(np.int64)
            w = f.create_group("windows")
            w["start_sample"] = cat("win_start", np.int64); w["trigger_sample"] = cat("win_trig", np.int16)
            s = f.create_group("segments")
            s["pmt"] = cat("seg_pmt", np.uint16); s["window_in_example"] = cat("seg_win", np.uint8)
            s["start_sample"] = cat("seg_start", np.int16); s["length"] = cat("seg_len", np.uint16)
            lens = s["length"][()].astype(np.int64)
            s["sample_off"] = np.concatenate(([0], np.cumsum(lens))).astype(np.int64)
            f.create_dataset("samples", data=cat("samples", np.int16), compression="gzip", compression_opts=4, chunks=True)
        os.replace(path_h5 + ".tmp", path_h5)
        T = {k: np.asarray([t[k] for t in self.truth]) for k in self.truth[0]} if n else {}
        np.savez_compressed(path_truth, **{f"t_{k}": v for k, v in T.items()},
                            pe_off=np.concatenate(([0], np.cumsum(self.npe))).astype(np.int64),
                            pe_pmt=np.concatenate(self.pe["pmt"]) if n else np.zeros(0, np.uint16),
                            pe_win=np.concatenate(self.pe["win"]) if n else np.zeros(0, np.uint8),
                            pe_t=np.concatenate(self.pe["t"]) if n else np.zeros(0, np.float32),
                            pe_label=np.concatenate(self.pe["label"]) if n else np.zeros(0, np.int8),
                            meta_json=np.array(json.dumps(meta)))


def base_truth(**kw):
    t = {"cls": -1, "sample_a": "", "sample_b": "", "split": "", "seed_a": -1, "evid_a": -1, "seed_b": -1, "evid_b": -1,
         "prompt_x": np.nan, "prompt_y": np.nan, "prompt_z": np.nan, "delayed_x": np.nan, "delayed_y": np.nan, "delayed_z": np.nan,
         "dt_true_ns": np.nan, "n_target": -1, "overlap": -1, "ep_ke": np.nan, "n_ke": np.nan, "edep_a": np.nan, "edep_b": np.nan,
         "q_close": -1, "pair_i": "", "pair_j": "", "importance": np.nan, "N_ij": np.nan, "M_ij": np.nan, "triggered": True,
         "prompt_nhit": -1}
    t.update(kw)
    return t


def mode_events(a, cfg):
    d = np.load(a.chunk)
    n_pmt = len(d["pmt_x"])
    sh = Shard()
    cnt = {}                        # per split: recorded, untriggered (digitiser), fail_prompt, kept, n_target of kept
    for i in range(len(d["evid"])):
        seed, evid = int(d["seed"][i]), int(d["evid"][i])
        rng = np.random.default_rng([a.digi_seed, 7, seed, evid])
        s = slice(d["pe_off"][i], d["pe_off"][i + 1])
        lab = np.where(d["pe_delayed"][s], 2, 1).astype(np.int8)
        res = digitize_example([(d["pe_pmt"][s], d["pe_t"][s].astype(np.float64), lab)], n_pmt, cfg, rng)
        vx, vy, vz = (float(d[f"vtx_{k}"][i]) for k in "xyz")
        sp = split_of(np.array([seed]), np.array([phi_deg(vx, vy)]))[0]
        tr = base_truth(cls=CLASS_OF[a.sample], sample_a=a.sample, split=sp, seed_a=seed, evid_a=evid,
                        prompt_x=vx, prompt_y=vy, prompt_z=vz,
                        delayed_x=float(d["n_x1"][i]), delayed_y=float(d["n_y1"][i]), delayed_z=float(d["n_z1"][i]),
                        dt_true_ns=float(d["n_t1"][i] - d["vtx_t"][i]), n_target=int(d["n_target"][i]), overlap=int(d["overlap"][i]),
                        ep_ke=float(d["ep_ke"][i]), n_ke=float(d["n_ke"][i]), edep_a=float(d["edep"][i]))
        tr["triggered"] = res is not None
        c = cnt.setdefault(sp, {"recorded": 0, "untriggered": 0, "fail_prompt": 0, "kept": 0, "n_target_kept": [0, 0, 0, 0]})
        c["recorded"] += 1
        if res is None:
            sh.truth_untriggered = getattr(sh, "truth_untriggered", 0) + 1; c["untriggered"] += 1
            continue
        tr["prompt_nhit"] = prompt_nhit(res, cfg)
        if tr["prompt_nhit"] < PROMPT_NHIT_MIN:
            sh.n_fail_prompt = getattr(sh, "n_fail_prompt", 0) + 1; c["fail_prompt"] += 1
            continue
        c["kept"] += 1; c["n_target_kept"][max(0, min(3, tr["n_target"]))] += 1
        sh.add(res, tr)
    allsp = split_of(d["seed"].astype(np.int64), np.degrees(np.arctan2(d["vtx_y"], d["vtx_x"])) % 360.0)
    meta = {"mode": "events", "sample": a.sample, "chunk": a.chunk, "n_events_in_chunk": int(len(d["evid"])), "n_generated": NEV_PER_CHUNK,
            "n_events_by_split": {k: int((allsp == k).sum()) for k in SPLIT_CODE},
            "n_untriggered": int(getattr(sh, "truth_untriggered", 0)), "n_fail_prompt": int(getattr(sh, "n_fail_prompt", 0)),
            "prompt_nhit_min": PROMPT_NHIT_MIN, "prompt_rule": PROMPT_RULE, "counts_by_split": cnt, "digitizer": cfg.as_dict(), "digi_seed": a.digi_seed, "argv": sys.argv}
    sh.write(a.out + ".h5", a.out + ".truth.npz", meta)
    print(json.dumps({"out": a.out, "examples": len(sh.truth), "untriggered": meta["n_untriggered"]}))


def mode_scan(a, cfg):
    d = np.load(a.chunk)
    n_pmt = len(d["pmt_x"])
    out = {k: [] for k in ("seed", "evid", "triggered", "prompt_nhit", "x", "y", "z", "split")}
    for i in range(len(d["evid"])):
        seed, evid = int(d["seed"][i]), int(d["evid"][i])
        s = slice(d["pe_off"][i], d["pe_off"][i + 1])
        res = dg.digitize(d["pe_pmt"][s], d["pe_t"][s].astype(np.float64), np.ones(s.stop - s.start, np.int8), n_pmt, cfg,
                          np.random.default_rng([a.digi_seed, 11, seed, evid])) if s.stop > s.start else None
        vx, vy, vz = (float(d[f"vtx_{k}"][i]) for k in "xyz")
        out["seed"].append(seed); out["evid"].append(evid); out["triggered"].append(res is not None)
        out["prompt_nhit"].append(prompt_nhit(res, cfg) if res is not None else 0)
        out["x"].append(vx); out["y"].append(vy); out["z"].append(vz)
        out["split"].append(split_of(np.array([seed]), np.array([phi_deg(vx, vy)]))[0])
    np.savez_compressed(a.out, sample=np.array(a.sample), chunk=np.array(a.chunk), n_generated=NEV_PER_CHUNK,
                        **{k: np.asarray(v) for k, v in out.items()})
    print(json.dumps({"out": a.out, "events": len(out["seed"]), "triggered": int(np.sum(out["triggered"]))}))


def load_pools(scan_dir):
    """Singles pools from the scan. 'first' = singles that pass the prompt condition alone (pair member A);
    'second' = singles that trigger (member B). Fractions per sample: f_prompt, f_trig (of generated decays)."""
    pools = {"first": {}, "second": {}}
    cnt = {}
    for f in sorted(glob.glob(os.path.join(scan_dir, "*.scan.npz"))):
        s = np.load(f)
        smp = str(s["sample"])
        c = cnt.setdefault(smp, {"generated": 0, "triggered": 0, "prompt": 0})
        trig = s["triggered"].astype(bool); prm = trig & (s["prompt_nhit"] >= PROMPT_NHIT_MIN)
        c["generated"] += int(s["n_generated"]); c["triggered"] += int(trig.sum()); c["prompt"] += int(prm.sum())
        xyz = np.column_stack([s["x"], s["y"], s["z"]]) / 1000.0
        for role, m in (("first", prm), ("second", trig)):
            k = np.flatnonzero(m)
            if len(k):
                pools[role].setdefault(smp, []).append((str(s["chunk"]), s["evid"][k], xyz[k], s["split"][k], s["seed"][k]))
    frac = {smp: {"f_trig": c["triggered"] / c["generated"], "f_prompt": c["prompt"] / c["generated"]} for smp, c in cnt.items()}
    return pools, frac, cnt


def region_mask(xyz, split):
    """True where a vertex lies in the phi region of `split` (the same wedges as train_stage1.split_of)."""
    from train_stage1 import WEDGES
    phi = np.degrees(np.arctan2(xyz[:, 1], xyz[:, 0])) % 360.0
    inw = {k: (phi >= lo) & (phi < hi) for k, (lo, hi) in WEDGES.items()}
    if split in inw:
        return inw[split]
    return ~(inw["val_wedge"] | inw["test_wedge"])


def pair_plan(pools, frac, split, budget):
    """Per ordered pair (i first, j second) with N_ij >= 1/yr: N_ij = (A_i f_prompt,i)(A_j f_trig,j) T yr; close-pair
    count C_ij and pool sizes for one split; M_ij allocated proportional to sqrt(N_ij) (min 200)."""
    from scipy.spatial import cKDTree

    def flat(role):
        out = {}
        for smp, parts in pools[role].items():
            xyz = np.vstack([p[2] for p in parts]); sp = np.concatenate([p[3] for p in parts])
            if (sp == split).any():
                out[smp] = xyz[sp == split]
        return out
    F, S = flat("first"), flat("second")
    S_all = {smp: np.vstack([p[2] for p in parts]) for smp, parts in pools["second"].items()}     # every split (geometry only)
    in_reg = lambda xyz: region_mask(xyz, split)
    plan = []
    for i in F:
        for j in S:
            n_ij = (rates.activity_bq(i) * frac[i]["f_prompt"]) * (rates.activity_bq(j) * frac[j]["f_trig"]) * T_PAIR_NS * 1e-9 * rates.YEAR_S
            if n_ij < 1.0:
                continue
            close = int(cKDTree(F[i]).count_neighbors(cKDTree(S[j]), CLOSE_M))
            # Pairs are formed within one split (no decay in two splits), so B is confined to the split's phi region, which
            # over-represents close pairs (~6x in a 45 deg wedge; review 2026-11-13). Post-stratify: close and far pairs are
            # reweighted to their TRUE shares, with B anywhere in the detector (geometry from all scanned singles of j).
            tFi, tSj, tSall = cKDTree(F[i]), cKDTree(S[j]), cKDTree(S_all[j])
            radii = STRAT_EDGES[1:-1]
            cum_s = np.concatenate([[0], tFi.count_neighbors(tSj, radii), [len(F[i]) * len(S[j])]]).astype(float)
            cum_t = np.concatenate([[0], tFi.count_neighbors(tSall, radii), [len(F[i]) * len(S_all[j])]]).astype(float)
            p_split_k = np.diff(cum_s) / (len(F[i]) * len(S[j])); p_true_k = np.diff(cum_t) / (len(F[i]) * len(S_all[j]))
            strat = np.where(p_split_k > 0, p_true_k / np.where(p_split_k > 0, p_split_k, 1), 1.0)
            mid = int(cum_s[np.searchsorted(STRAT_EDGES, MID_M)] - cum_s[np.searchsorted(STRAT_EDGES, CLOSE_M)])
            g_j = float(in_reg(S_all[j]).mean())
            plan.append({"i": i, "j": j, "N_ij": n_ij, "C_ij": close, "C_mid": mid, "n_i": len(F[i]), "n_j": len(S[j]), "n_j_all": len(S_all[j]),
                         "g_j": g_j, "strat_edges_m": STRAT_EDGES[:-1].tolist(), "p_true_k": p_true_k.tolist(), "p_split_k": p_split_k.tolist(),
                         "strat_k": strat.tolist(), "empty_split_bins_with_true_rate": [int(k) for k in np.flatnonzero((p_split_k == 0) & (p_true_k > 0))]})
    if plan:
        sq = np.array([np.sqrt(p["N_ij"]) for p in plan])
        for p, mm in zip(plan, np.maximum((budget * sq / sq.sum()).astype(int), 200)):
            p["M_ij"] = int(mm)
    return plan


SPLIT_CODE = {"train": 0, "val_random": 1, "val_wedge": 2, "test_random": 3, "test_wedge": 4}


def draw_dt(rng, mix, tau):
    """Accidental time offset (ns) and its importance factor u/q. mix = 0: dt ~ U(0, T) (factor 1, the original rule).
    mix > 0 (v3e, agreed with the SIDERIUS instance 2026-11-14): q = mix * Exp(tau) truncated to [0, T) + (1 - mix) * U(0, T),
    tau = the IBD capture-time constant fitted on train geo (5.3 us). Exact: every pair carries u(dt)/q(dt) in its weight,
    so the weighted rates are unchanged while short-dt pairs (where IBDs are) are sampled more densely."""
    T = T_PAIR_NS
    if mix <= 0:
        return float(rng.uniform(0.0, T)), 1.0
    norm = 1.0 - np.exp(-T / tau)
    if rng.random() < mix:
        dt = float(-tau * np.log(1.0 - rng.random() * norm))
    else:
        dt = float(rng.uniform(0.0, T))
    q = mix * np.exp(-dt / tau) / (tau * norm) + (1.0 - mix) / T
    return dt, float((1.0 / T) / q)


def mode_accidentals(a, cfg):
    from scipy.spatial import cKDTree
    pools, frac, counts = load_pools(a.scan_dir)
    plan = pair_plan(pools, frac, a.split, a.budget)
    ntask = a.n_tasks
    rng = np.random.default_rng([a.digi_seed, 13, a.task, SPLIT_CODE[a.split]])
    # preload the photoelectrons of every triggered single in this split (each chunk file read once)
    flat = {"first": {}, "second": {}}
    for role in ("first", "second"):
      for smp, parts in pools[role].items():
        rows = []
        for chunk, evid, xyz, sp, seed in parts:
            ks = np.flatnonzero(sp == a.split)
            if len(ks) == 0:
                continue
            d = np.load(chunk)
            pe_off, pe_pmt, pe_t, evids, edep = d["pe_off"], d["pe_pmt"], d["pe_t"], d["evid"], d["edep"]
            for k in ks:
                e = int(np.flatnonzero(evids == evid[k])[0])
                rows.append({"seed": int(seed[k]), "evid": int(evid[k]), "xyz": xyz[k], "edep": float(edep[e]),
                             "pmt": pe_pmt[pe_off[e]:pe_off[e + 1]].copy(), "t": pe_t[pe_off[e]:pe_off[e + 1]].astype(np.float64)})
        flat[role][smp] = rows
    sh = Shard()
    for p in plan:
        i, j = p["i"], p["j"]
        Pi, Pj = flat["first"][i], flat["second"][j]
        Xi, Xj = np.array([r["xyz"] for r in Pi]), np.array([r["xyz"] for r in Pj])
        tj = cKDTree(Xj)
        nb_count = tj.query_ball_point(Xi, CLOSE_M, return_length=True).astype(float)
        p_i = nb_count / nb_count.sum() if nb_count.sum() > 0 else None   # uniform over close pairs: i ~ its close count
        mid_count = tj.query_ball_point(Xi, MID_M, return_length=True).astype(float) - nb_count
        p_mid = mid_count / mid_count.sum() if mid_count.sum() > 0 else None   # uniform over 3-6 m pairs
        m_task = int(np.ceil(p["M_ij"] / ntask))
        for _ in range(m_task):
            while True:                                             # never overlay a decay with itself
                u = rng.random()
                if p_i is not None and u < ALPHA_CLOSE:
                    ai = int(rng.choice(len(Pi), p=p_i))
                    bj = int(rng.choice(tj.query_ball_point(Xi[ai], CLOSE_M)))
                elif p_mid is not None and u < ALPHA_CLOSE + ALPHA_MID:
                    ai = int(rng.choice(len(Pi), p=p_mid))
                    shell = sorted(set(tj.query_ball_point(Xi[ai], MID_M)) - set(tj.query_ball_point(Xi[ai], CLOSE_M)))
                    bj = int(rng.choice(shell))
                else:
                    ai, bj = int(rng.integers(len(Pi))), int(rng.integers(len(Pj)))
                if not (i == j and Pi[ai]["seed"] == Pj[bj]["seed"] and Pi[ai]["evid"] == Pj[bj]["evid"]):
                    break
            A, B = Pi[ai], Pj[bj]
            close = bool(np.linalg.norm(A["xyz"] - B["xyz"]) < CLOSE_M)
            dt, dt_w = draw_dt(rng, a.dt_mix, a.dt_tau)
            srcs = [(A["pmt"], A["t"], np.full(len(A["t"]), 1, np.int8)), (B["pmt"], B["t"] + dt, np.full(len(B["t"]), 2, np.int8))]
            res = digitize_example(srcs, 12505, cfg, np.random.default_rng([a.digi_seed, 17, SPLIT_CODE[a.split], a.task, len(sh.truth),
                                                                            A["seed"], A["evid"], B["seed"], B["evid"]]))
            dd = float(np.linalg.norm(A["xyz"] - B["xyz"]))
            is_mid = (dd >= CLOSE_M) and (dd < MID_M)
            a_c = ALPHA_CLOSE if p_i is not None else 0.0
            a_m = ALPHA_MID if p_mid is not None else 0.0
            q = a_c * close / max(p["C_ij"], 1) + a_m * is_mid / max(p["C_mid"], 1) + (1 - a_c - a_m) / (p["n_i"] * p["n_j"])
            imp = (1.0 / (p["n_i"] * p["n_j"])) / q
            kbin = int(np.searchsorted(STRAT_EDGES, dd, side="right") - 1)
            tr = base_truth(cls=4, sample_a=i, sample_b=j, split=a.split, seed_a=A["seed"], evid_a=A["evid"], seed_b=B["seed"], evid_b=B["evid"],
                            prompt_x=A["xyz"][0] * 1000, prompt_y=A["xyz"][1] * 1000, prompt_z=A["xyz"][2] * 1000,
                            delayed_x=B["xyz"][0] * 1000, delayed_y=B["xyz"][1] * 1000, delayed_z=B["xyz"][2] * 1000,
                            dt_true_ns=dt, edep_a=A["edep"], edep_b=B["edep"], q_close=int(close), pair_i=i, pair_j=j)
            tr["importance"] = imp * p["strat_k"][kbin] * dt_w; tr["N_ij"] = p["N_ij"]; tr["M_ij"] = m_task * ntask
            tr["triggered"] = res is not None
            if res is not None:
                tr["prompt_nhit"] = prompt_nhit(res, cfg)
                if tr["prompt_nhit"] >= PROMPT_NHIT_MIN:
                    sh.add(res, tr)
    meta = {"mode": "accidentals", "split": a.split, "task": a.task, "n_tasks": ntask, "plan": plan, "fractions": frac, "counts": counts, "prompt_nhit_min": PROMPT_NHIT_MIN, "alpha_close": ALPHA_CLOSE, "alpha_mid": ALPHA_MID,
            "dt_mix": a.dt_mix, "dt_tau_ns": a.dt_tau,
            "activity_bq": {k: rates.activity_bq(k) for k in pools["second"]}, "digitizer": cfg.as_dict(), "digi_seed": a.digi_seed, "argv": sys.argv}
    sh.write(a.out + ".h5", a.out + ".truth.npz", meta)
    print(json.dumps({"out": a.out, "examples": len(sh.truth), "plan": [(p["i"], p["j"], round(p["N_ij"]), p["M_ij"]) for p in plan]}))


def mode_geometry(a, cfg):
    """pmt_geometry.h5: PMT id -> position (mm) and facing direction, from any *.events.npz."""
    import h5py
    d = np.load(a.chunk)
    with h5py.File(a.out + ".tmp", "w") as f:
        for k in ("x", "y", "z", "u", "v", "w"):
            f[k] = d[f"pmt_{k}"].astype(np.float32)
        f.attrs["units"] = "mm; u,v,w unit vector the PMT faces (inward)"
        f.attrs["n_pmt"] = int(len(d["pmt_x"]))
    os.replace(a.out + ".tmp", a.out)
    print(json.dumps({"out": a.out, "n_pmt": int(len(d["pmt_x"]))}))


GROUPS = {"train": ["train"], "val": ["val_random", "val_wedge"], "test": ["test_random", "test_wedge"],
          "dev": ["train", "val_random", "val_wedge", "test_random", "test_wedge"]}   # dev: --dev-per-class examples per (split, class)
DETECTOR = {"detector": "OBD17kt v1 geometry, GEL-filled glass shields, LY 10000/MeV, 1.0 wt% 6Li LAB+PPO 3 g/L",
            "optics": "OPTICS_OBD.ratdb sha256 84128bc2... (LAB re-emission < 340 nm only; PPO scaling 1.2; physics audit 2026-11-13)",
            "simulation": "ratpac-two 4.4.0, BASE_SEED 41-63 production (TAG suffix _gel)"}


def mode_merge(a, cfg):
    """Shards -> <group>_<part>.h5 (waveforms) + <group>_<part>.labels.h5 (truth, weights, real PEs)."""
    import h5py
    shards = sorted(glob.glob(os.path.join(a.shard_dir, "*.h5")))
    shards = [s for s in shards if not s.endswith(".labels.h5")]
    # simulated events per class and split (IBD / alpha,n weights)
    nsim, rec, counts = {}, {}, {}
    for sh in shards:
        with h5py.File(sh, "r") as f:
            m = json.loads(f.attrs["meta_json"])
        if m["mode"] == "events":
            for sp, n in m["n_events_by_split"].items():
                nsim[(m["sample"], sp)] = nsim.get((m["sample"], sp), 0) + n
            r = rec.setdefault(m["sample"], [0, 0]); r[0] += m["n_events_in_chunk"]; r[1] += m.get("n_generated", NEV_PER_CHUNK)
            for sp_, c in m.get("counts_by_split", {}).items():
                agg = counts.setdefault(f"{m['sample']}|{sp_}", {"recorded": 0, "untriggered": 0, "fail_prompt": 0, "kept": 0, "n_target_kept": [0, 0, 0, 0]})
                for k_ in ("recorded", "untriggered", "fail_prompt", "kept"):
                    agg[k_] += c[k_]
                agg["n_target_kept"] = [x + y for x, y in zip(agg["n_target_kept"], c["n_target_kept"])]
    # events.npz holds only events with >= 1 ratpac-recorded trigger. Scale the per-split counts up to generated events
    # (assumed split-uniform), so efficiencies are not inflated by the unrecorded fraction (~0 for IBD, ~0.5 % for (alpha,n)).
    frac_rec = {k: v[0] / v[1] for k, v in rec.items()}
    rate = {"geoU": rates.SIGNAL_PER_YEAR["geoU"], "geoTh": rates.SIGNAL_PER_YEAR["geoTh"], "reactor": rates.REACTOR_PER_YEAR,
            "alphan": rates.alpha_n_per_year()}
    group_splits = GROUPS[a.group]
    quota = {}
    part, buf, nbuf_bytes = 0, [], 0
    summary = {"group": a.group, "parts": [], "nsim": {f"{k[0]}|{k[1]}": v for k, v in nsim.items()}, "recorded_fraction": frac_rec,
               "event_counts_by_class_split": counts, "prompt_nhit_min": PROMPT_NHIT_MIN, "prompt_rule": PROMPT_RULE}

    def flush():
        nonlocal part, buf, nbuf_bytes
        if not buf:
            return
        out = os.path.join(a.out, f"{a.group}_{part:03d}")
        _write_part(out, buf)
        n = sum(len(b["truth"]["t_cls"]) for b in buf)
        summary["parts"].append({"file": os.path.basename(out) + ".h5", "examples": int(n)})
        part += 1; buf = []; nbuf_bytes = 0

    for sh in shards:
        tr = np.load(sh[:-3] + ".truth.npz")
        if "t_split" not in tr.files:
            continue
        sel = np.flatnonzero(np.isin(tr["t_split"], group_splits))
        if a.group == "dev" and len(sel):
            keep = []
            for k in sel:
                key = (str(tr["t_split"][k]), int(tr["t_cls"][k]))
                if quota.get(key, 0) < a.dev_per_class:
                    quota[key] = quota.get(key, 0) + 1; keep.append(k)
            sel = np.array(keep, dtype=int)
        if len(sel) == 0:
            continue
        with h5py.File(sh, "r") as f:
            ex = _read_examples(f, sel)
        T = {k: tr[k][sel] for k in tr.files if k.startswith("t_")}
        cls = T["t_cls"]
        w = np.zeros(len(sel))
        for k, c in enumerate(cls):
            if c == 4:
                w[k] = T["t_N_ij"][k] * T["t_importance"][k] / T["t_M_ij"][k]
            else:
                name = CLASS_NAMES[c]
                w[k] = rate[name] * frac_rec.get(name, 1.0) / max(nsim.get((name, str(T["t_split"][k])), 0), 1)
        T["t_weight_per_year"] = w
        cr = summary.setdefault("accidental_weight_per_year_by_dtrue_bin", {})
        dtrue = np.sqrt((T["t_prompt_x"] - T["t_delayed_x"]) ** 2 + (T["t_prompt_y"] - T["t_delayed_y"]) ** 2 + (T["t_prompt_z"] - T["t_delayed_z"]) ** 2) / 1000.0
        for k, c in enumerate(cls):
            if c == 4:
                kb = int(np.searchsorted(STRAT_EDGES, dtrue[k], side="right") - 1)
                key = f"{T['t_split'][k]}|{STRAT_EDGES[kb]:g}-{STRAT_EDGES[kb + 1]:g}m"
                d_ = cr.setdefault(key, [0.0, 0]); d_[0] += float(w[k]); d_[1] += 1
        ws = summary.setdefault("weight_per_year_sums", {})
        for k, c in enumerate(cls):
            key = f"{T['t_split'][k]}|{CLASS_NAMES[c]}"
            ws[key] = ws.get(key, 0.0) + float(w[k])
        pe = _select_pe(tr, sel)
        buf.append({"ex": ex, "truth": T, "pe": pe})
        nbuf_bytes += ex["samples"].nbytes
        if nbuf_bytes > a.part_bytes:
            flush()
    flush()
    with open(os.path.join(a.out, f"{a.group}_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary)[:2000])


def _read_examples(f, sel):
    wo = f["examples/win_off"][()]; so = f["examples/seg_off_by_example"][()]
    ws, wt = f["windows/start_sample"][()], f["windows/trigger_sample"][()]
    sp_, sw, ss, sl, soff = (f[f"segments/{k}"][()] for k in ("pmt", "window_in_example", "start_sample", "length", "sample_off"))
    samples = f["samples"][()]
    out = {"n_win": [], "win_start": [], "win_trig": [], "seg_pmt": [], "seg_win": [], "seg_start": [], "seg_len": [], "samples": []}
    for e in sel:
        out["n_win"].append(wo[e + 1] - wo[e]); out["win_start"].append(ws[wo[e]:wo[e + 1]]); out["win_trig"].append(wt[wo[e]:wo[e + 1]])
        a0, a1 = so[e], so[e + 1]
        out["seg_pmt"].append(sp_[a0:a1]); out["seg_win"].append(sw[a0:a1]); out["seg_start"].append(ss[a0:a1]); out["seg_len"].append(sl[a0:a1])
        out["samples"].append(samples[soff[a0]:soff[a1]])
    return {k: (np.asarray(v) if k == "n_win" else np.concatenate(v)) for k, v in out.items()} | {"n_seg": np.array([so[e + 1] - so[e] for e in sel])}


def _select_pe(tr, sel):
    off = tr["pe_off"]
    idx = np.concatenate([np.arange(off[e], off[e + 1]) for e in sel]) if len(sel) else np.zeros(0, int)
    return {"n": np.array([off[e + 1] - off[e] for e in sel]), **{k: tr[k][idx] for k in ("pe_pmt", "pe_win", "pe_t", "pe_label")}}


def _write_part(out, buf):
    import h5py
    cat = lambda key, sub: np.concatenate([b[sub][key] for b in buf])
    n_win, n_seg = cat("n_win", "ex"), cat("n_seg", "ex")
    seg_len = cat("seg_len", "ex").astype(np.int64)
    with h5py.File(out + ".h5.tmp", "w") as f:
        f.attrs["format"] = "OBD17kt hackathon waveforms v1: see docs/DATASET.md"
        f.attrs["detector_json"] = json.dumps(DETECTOR)
        f["examples/win_off"] = np.concatenate(([0], np.cumsum(n_win))).astype(np.int64)
        f["examples/seg_off"] = np.concatenate(([0], np.cumsum(n_seg))).astype(np.int64)
        f["windows/start_sample"] = cat("win_start", "ex"); f["windows/trigger_sample"] = cat("win_trig", "ex")
        f["segments/pmt"] = cat("seg_pmt", "ex"); f["segments/window_in_example"] = cat("seg_win", "ex")
        f["segments/start_sample"] = cat("seg_start", "ex"); f["segments/length"] = seg_len.astype(np.uint16)
        f["segments/sample_off"] = np.concatenate(([0], np.cumsum(seg_len))).astype(np.int64)
        f.create_dataset("samples", data=cat("samples", "ex"), compression="gzip", compression_opts=4, chunks=True)
    os.replace(out + ".h5.tmp", out + ".h5")
    with h5py.File(out + ".labels.h5.tmp", "w") as f:
        keys = buf[0]["truth"].keys()
        for k in keys:
            v = np.concatenate([b["truth"][k] for b in buf])
            f[f"truth/{k[2:]}"] = v.astype("S") if v.dtype.kind in "UO" else v
        n_pe = np.concatenate([b["pe"]["n"] for b in buf])
        f["real_pe/off"] = np.concatenate(([0], np.cumsum(n_pe))).astype(np.int64)
        for k in ("pe_pmt", "pe_win", "pe_t", "pe_label"):
            f.create_dataset(f"real_pe/{k[3:]}", data=np.concatenate([b["pe"][k] for b in buf]), compression="gzip", compression_opts=4, chunks=True)
    os.replace(out + ".labels.h5.tmp", out + ".labels.h5")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["scan", "events", "accidentals", "merge", "geometry"])
    ap.add_argument("--shard-dir")
    ap.add_argument("--group", choices=list(GROUPS))
    ap.add_argument("--part-bytes", type=float, default=2.0e9)
    ap.add_argument("--dev-per-class", type=int, default=300)
    ap.add_argument("--chunk")
    ap.add_argument("--sample")
    ap.add_argument("--scan-dir")
    ap.add_argument("--split")
    ap.add_argument("--task", type=int, default=0)
    ap.add_argument("--n-tasks", type=int, default=1)
    ap.add_argument("--budget", type=int, default=20000, help="accidental pairs per split (all tasks together)")
    ap.add_argument("--digi-seed", type=int, default=1)
    ap.add_argument("--dt-mix", type=float, default=0.0, help="accidental dt importance sampling: weight of the Exp(tau) part (0 = uniform)")
    ap.add_argument("--dt-tau", type=float, default=5300.0, help="ns; IBD capture-time constant for --dt-mix")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    cfg = dg.DigiConfig()
    {"scan": mode_scan, "events": mode_events, "accidentals": mode_accidentals, "merge": mode_merge, "geometry": mode_geometry}[a.mode](a, cfg)


if __name__ == "__main__":
    main()
