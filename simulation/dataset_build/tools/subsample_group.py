#!/usr/bin/env python3
"""Make a smaller val or test group from a full build (user decision 2026-11-14: the kit's evaluate step must finish within
30 min, and the full v3b val group has ~155k examples).

Per (sub-split, class), keep at most CAP[class] examples, uniformly at random (seeded), and multiply weight_per_year
by n_class_in_subsplit / n_kept. Every sub-split then still represents one year, and the weighted rates are unbiased.
Accidentals: without --acc-alloc they are subsampled uniformly within the class. With --acc-alloc, per true-separation
bin (build_dataset.STRAT_EDGES; all 8 bins must be given, and each bin with examples keeps >= 1), weight x available/kept
per (sub-split, class, bin). This is a Horvitz-Thompson estimate under uniform selection inside each stratum.
Output: <group>_000.h5 + <group>_000.labels.h5 in the published format (via build_dataset._write_part), plus
<group>_subsample.json with caps, counts, factors and weight sums.
usage: subsample_group.py --group val --in-dir dataset_v3b/final --out-dir dataset_v3c/final [--seed 20261114]
"""
import argparse
import glob
import json
import os

import h5py
import numpy as np

import build_dataset as bd
from h5reader import WaveformFile

CAP = {0: 3000, 1: 1000, 2: 1000, 3: 1500, 4: 9000}   # per sub-split (accidentals 9000 from v3d: agreed 2026-11-14): geoU, geoTh, reactor, (alpha,n), accidental
# Optional per-bin allocation for accidentals (--acc-alloc JSON {"lo-hi": n, ...} over build_dataset.STRAT_EDGES bins).
# Weights are then x (available/kept) per (sub-split, class, BIN): unbiased, and draws go to the bins where leakage
# resolution matters (review by the SIDERIUS instance, 2026-11-14).


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--group", required=True, choices=["val", "test"])
    ap.add_argument("--in-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seed", type=int, default=20261114)
    ap.add_argument("--acc-alloc", help='JSON per-bin accidental counts per sub-split, keys "lo-hi" in m (e.g. "0-1.5")')
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(a.in_dir, f"{a.group}_[0-9][0-9][0-9].h5")))
    # pass 1: inventory (file index, example index, split, class)
    inv = []
    w_in = {}
    alloc = None
    if a.acc_alloc:
        edges = bd.STRAT_EDGES
        names = [f"{edges[k]:g}-{edges[k + 1]:g}" for k in range(len(edges) - 1)]
        req = json.loads(a.acc_alloc)
        if set(req) != set(names):
            raise SystemExit(f"--acc-alloc must name exactly the bins {names}; got {sorted(req)}")
        alloc = {names.index(k): int(v) for k, v in req.items()}
        if min(alloc.values()) < 1:
            raise SystemExit("--acc-alloc: every bin needs >= 1 draw (a zero would silently drop that bin's weight)")
    for fi, f in enumerate(files):
        L = h5py.File(f[:-3] + ".labels.h5", "r")
        sp, cl = L["truth/split"][()].astype(str), L["truth/cls"][()]
        dd = np.sqrt(sum((L[f"truth/prompt_{c}"][()] - L[f"truth/delayed_{c}"][()]) ** 2 for c in "xyz")) / 1000.0
        kb = np.searchsorted(bd.STRAT_EDGES, dd, side="right") - 1
        bad = (cl == 4) & (~np.isfinite(dd) | (kb < 0) | (kb >= len(bd.STRAT_EDGES) - 1))
        if bad.any():
            raise SystemExit(f"{f}: {int(bad.sum())} accidental examples with invalid true separation (NaN or out of range)")
        for e in range(len(cl)):
            key_in = f"{sp[e]}|{bd.CLASS_NAMES[int(cl[e])]}"; w_in[key_in] = w_in.get(key_in, 0.0) + float(L["truth/weight_per_year"][e])
        inv += [(fi, e, sp[e], int(cl[e]), int(kb[e]) if (alloc and cl[e] == 4) else -1) for e in range(len(cl))]
    rng = np.random.default_rng(a.seed)
    keep, factor, counts = set(), {}, {}
    for key in sorted({(s, c, b) for _, _, s, c, b in inv}):
        idx = [i for i, t in enumerate(inv) if (t[2], t[3], t[4]) == key]
        k = min(len(idx), alloc[key[2]] if (alloc and key[1] == 4) else CAP[key[1]])
        if k < 1:
            raise SystemExit(f"stratum {key} has {len(idx)} examples but 0 would be kept")
        chosen = rng.choice(len(idx), k, replace=False)
        keep.update(idx[j] for j in chosen)
        factor[key] = len(idx) / k
        counts[f"{key[0]}|{bd.CLASS_NAMES[key[1]]}" + (f"|bin{key[2]}" if key[2] >= 0 else "")] = {"available": len(idx), "kept": k, "weight_factor": len(idx) / k}
    # pass 2: copy the kept examples, in inventory order (deterministic)
    buf, wsum, acc_bins = [], {}, {}
    for fi, f in enumerate(files):
        sel = sorted(e for (i, (ffi, e, s, c, b)) in enumerate(inv) if ffi == fi and i in keep)
        binof = {e: b for (ffi, e, s, c, b) in inv if ffi == fi}
        if not sel:
            continue
        W = WaveformFile(f, f[:-3] + ".labels.h5")
        ex = {k: [] for k in ("n_win", "win_start", "win_trig", "seg_pmt", "seg_win", "seg_start", "seg_len", "samples", "n_seg")}
        pe = {"n": [], "pe_pmt": [], "pe_win": [], "pe_t": [], "pe_label": []}
        for e in sel:
            r = W.example(e, with_truth=True)
            ex["n_win"].append(len(r["win_start"])); ex["n_seg"].append(len(r["seg_pmt"]))
            for k in ("win_start", "win_trig", "seg_pmt", "seg_win", "seg_start", "seg_len", "samples"):
                ex[k].append(r[k])
            pe["n"].append(len(r["pe_t"]))
            for k in ("pmt", "win", "t", "label"):
                pe["pe_" + k].append(r["pe_" + k])
        T = {"t_" + k: v[sel] for k, v in W.truth.items()}
        f_ = np.array([factor[(s.decode() if isinstance(s, bytes) else str(s), int(c), binof[e])] for s, c, e in zip(T["t_split"], T["t_cls"], sel)])
        T["t_weight_per_year"] = T["t_weight_per_year"] * f_
        for s, c, w, e in zip(T["t_split"], T["t_cls"], T["t_weight_per_year"], sel):
            s_ = s.decode() if isinstance(s, bytes) else str(s)
            kk = f"{s_}|{bd.CLASS_NAMES[int(c)]}"; wsum[kk] = wsum.get(kk, 0.0) + float(w)
            if int(c) == 4:
                d_ = np.sqrt((W.truth["prompt_x"][e] - W.truth["delayed_x"][e]) ** 2 + (W.truth["prompt_y"][e] - W.truth["delayed_y"][e]) ** 2
                             + (W.truth["prompt_z"][e] - W.truth["delayed_z"][e]) ** 2) / 1000.0
                kb_ = int(np.searchsorted(bd.STRAT_EDGES, d_, side="right") - 1)
                bkey = f"{s_}|{bd.STRAT_EDGES[kb_]:g}-{bd.STRAT_EDGES[kb_ + 1]:g}m"
                bw = acc_bins.setdefault(bkey, [0.0, 0]); bw[0] += float(w); bw[1] += 1
        T = {k: (v.astype(str) if v.dtype.kind == "S" else v) for k, v in T.items()}
        exd = {k: (np.asarray(v) if k in ("n_win", "n_seg") else np.concatenate(v)) for k, v in ex.items()}
        ped = {"n": np.asarray(pe["n"]), **{k: np.concatenate(v) for k, v in pe.items() if k != "n"}}
        buf.append({"ex": exd, "truth": T, "pe": ped})
    out = os.path.join(a.out_dir, f"{a.group}_000")
    bd._write_part(out, buf)
    with h5py.File(files[0], "r") as f0, h5py.File(out + ".h5", "a") as fo:
        if "detector_json" in f0.attrs:
            fo.attrs["detector_json"] = f0.attrs["detector_json"]
        fo.attrs["subsample_json"] = json.dumps({"caps": {bd.CLASS_NAMES[k]: v for k, v in CAP.items()}, "seed": a.seed, "source": files,
                                                 "acc_alloc_per_bin": json.loads(a.acc_alloc) if a.acc_alloc else None,
                                                 "rule": "per (sub-split, class[, true-separation bin for accidentals]) keep min(available, cap) uniformly at random (seed); weight x available/kept"})
    json.dump({"caps": {bd.CLASS_NAMES[k]: v for k, v in CAP.items()}, "acc_alloc_per_bin": json.loads(a.acc_alloc) if a.acc_alloc else None,
               "rule": "per (sub-split, class[, d_true bin for accidentals]) keep min(available, cap) uniformly at random (seed); weight x available/kept",
               "seed": a.seed, "counts": counts, "weight_per_year_sums_input": w_in,
               "accidental_weight_per_year_by_dtrue_bin": acc_bins, "weight_per_year_sums": wsum,
               "examples": len(keep), "source_files": files}, open(os.path.join(a.out_dir, f"{a.group}_subsample.json"), "w"), indent=1)
    for k in sorted(w_in):
        print(f"  {k}: input {w_in[k]:.4g} /yr -> output {wsum.get(k, 0.0):.4g} /yr")
    print(json.dumps({"out": out, "examples": len(keep)}))


if __name__ == "__main__":
    main()
