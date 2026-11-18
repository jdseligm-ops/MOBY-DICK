#!/usr/bin/env python3
"""Stage 1 (hit cleaner): random forest on aligned Layout-B rows, "real photon vs dark/electronic noise".

Splits (agreed 2026-11-13: by event and by chunk, plus held-out phi wedges of the detector):
  val_wedge   vertex phi in [0, 45) deg                     region hold-out, used for selection
  test_wedge  vertex phi in [180, 225) deg                  final region test, never used for choices
  outside both wedges, by chunk seed % 10: 0-7 train, 8 val_random, 9 test_random
A wedge score below the random-split score of the same role measures memorisation of PMT position.
Shortcut tests (--shortcuts): shuffled training labels (expect mean prediction equal for true-real and true-noise
rows; AUC alone is unreliable here, see docs/STAGE1_RESULTS.md), geometry/time columns only
(no waveforms), and own waveform only (no neighbours: what the neighbour slots add).
usage: train_stage1.py -o outdir [--trees 100 --depth 16 --max-train-rows 2000000 --jobs N --shortcuts] rows/*.npz
"""
import argparse
import json
import os
import pickle
import time

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score

WEDGES = {"val_wedge": (0.0, 45.0), "test_wedge": (180.0, 225.0)}


def load(files):
    parts = {k: [] for k in ("wave", "extra", "y", "real_frac", "win", "seed", "phi", "sample")}
    for f in files:
        d = np.load(f)
        ev = d["ev"]
        for k in ("wave", "extra", "y", "real_frac", "win"):
            parts[k].append(d[k])
        parts["seed"].append(d["ev_seed"][ev]); parts["phi"].append(d["ev_vtx_phi_deg"][ev])
        parts["sample"].append(np.full(len(ev), str(d["sample"])))
    return {k: np.concatenate(v) for k, v in parts.items()}


def split_of(seed, phi):
    out = np.full(len(seed), "", dtype=object)
    in_val_w = (phi >= WEDGES["val_wedge"][0]) & (phi < WEDGES["val_wedge"][1])
    in_test_w = (phi >= WEDGES["test_wedge"][0]) & (phi < WEDGES["test_wedge"][1])
    r = seed % 10
    out[:] = np.where(r <= 7, "train", np.where(r == 8, "val_random", "test_random"))
    out[in_val_w] = "val_wedge"
    out[in_test_w] = "test_wedge"
    return out


def metrics(y, p):
    out = {"rows": int(len(y)), "real_frac": float(y.mean()) if len(y) else None}
    if len(y) and 0 < y.mean() < 1:          # mean-prediction parity: the right check for the shuffled-label control
        out["mean_p_true_real"] = float(p[y == 1].mean()); out["mean_p_true_noise"] = float(p[y == 0].mean())
    if len(y) and 0 < y.mean() < 1:
        out["auc"] = float(roc_auc_score(y, p))
        out["acc@0.5"] = float(((p >= 0.5) == y).mean())
        # operating points: keep 99 % / 98 % / 95 % of real photons -> fraction of noise rows removed
        for keep in (0.99, 0.98, 0.95):
            thr = np.quantile(p[y == 1], 1 - keep)
            out[f"noise_removed@keep{int(keep * 100)}"] = float((p[y == 0] < thr).mean())
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("-o", "--outdir", required=True)
    ap.add_argument("--trees", type=int, default=100)
    ap.add_argument("--depth", type=int, default=16)
    ap.add_argument("--min-leaf", type=int, default=20)
    ap.add_argument("--max-train-rows", type=int, default=2_000_000)
    ap.add_argument("--seed", type=int, default=20261113)
    ap.add_argument("--jobs", type=int, default=int(os.environ.get("SLURM_CPUS_PER_TASK", os.cpu_count())))
    ap.add_argument("--shortcuts", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    t0 = time.perf_counter()
    D = load(a.files)
    X = np.hstack([D["wave"].astype(np.float32), D["extra"]])
    y = D["y"].astype(np.int8)
    sp = split_of(D["seed"], D["phi"])
    rng = np.random.default_rng(a.seed)
    tr = np.flatnonzero(sp == "train")
    if len(tr) > a.max_train_rows:
        tr = np.sort(rng.choice(tr, a.max_train_rows, replace=False))
    nwave = D["wave"].shape[1]
    res = {"args": vars(a), "load_s": time.perf_counter() - t0, "n_rows_by_split": {s: int((sp == s).sum()) for s in np.unique(sp)},
           "samples": {s: int((D["sample"] == s).sum()) for s in np.unique(D["sample"])}}

    def fit_eval(name, cols, ytr):
        rf = RandomForestClassifier(n_estimators=a.trees, max_depth=a.depth, min_samples_leaf=a.min_leaf,
                                    max_features="sqrt", n_jobs=a.jobs, random_state=a.seed)
        t = time.perf_counter(); rf.fit(X[tr][:, cols], ytr); tf = time.perf_counter() - t
        ev = {"fit_s": tf, "train_rows": int(len(tr)), "model_mib": len(pickle.dumps(rf)) / 2 ** 20}
        for s in ("train", "val_random", "val_wedge", "test_random", "test_wedge"):
            m = sp == s
            if m.any():
                p = rf.predict_proba(X[m][:, cols])[:, 1]
                ev[s] = metrics(y[m], p)
                if name == "full":
                    ev[s]["by_window"] = {f"win{w}": metrics(y[m & (D['win'] == w)], p[D['win'][m] == w]) for w in (0, 1)}
                    ev[s]["by_sample"] = {smp: metrics(y[m & (D['sample'] == smp)], p[D['sample'][m] == smp]) for smp in np.unique(D["sample"][m])}
        print(name, json.dumps({k: (v.get("auc") if isinstance(v, dict) else v) for k, v in ev.items()}), flush=True)
        return rf, ev

    all_cols = np.arange(X.shape[1])
    rf, res["full"] = fit_eval("full", all_cols, y[tr])
    with open(os.path.join(a.outdir, "stage1_rf.pkl"), "wb") as f:
        pickle.dump(rf, f)
    imp = rf.feature_importances_
    names = (["own"] + [f"nb{i}" for i in range(1, 7)] + (["ring2"] if nwave > 224 else []))
    res["importance_by_block"] = {n: float(imp[i * 32:(i + 1) * 32].sum()) for i, n in enumerate(names)}
    res["importance_extra"] = dict(zip(["t_onset_minus_trig_ns", "onset_rank", "is_wall", "z_over_25m", "cos_phi", "sin_phi", "rho_over_15m"],
                                       map(float, imp[nwave:])))
    if a.shortcuts:
        _, res["shuffled_labels"] = fit_eval("shuffled_labels", all_cols, rng.permutation(y[tr]))
        _, res["geometry_time_only"] = fit_eval("geometry_time_only", np.arange(nwave, X.shape[1]), y[tr])
        own = np.concatenate([np.arange(32), np.arange(nwave, X.shape[1])])
        _, res["own_waveform_only"] = fit_eval("own_waveform_only", own, y[tr])
    res["total_s"] = time.perf_counter() - t0
    with open(os.path.join(a.outdir, "stage1_results.json"), "w") as f:
        json.dump(res, f, indent=1)
    print("WROTE", os.path.join(a.outdir, "stage1_results.json"))


if __name__ == "__main__":
    main()
