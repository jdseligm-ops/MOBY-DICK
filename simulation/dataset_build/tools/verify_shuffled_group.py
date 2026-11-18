#!/usr/bin/env python3
"""Verify a shuffled evaluation file pair against its source (Z2 option B; companion of shuffle_eval_group.py).

Independent of the writer: it does NOT reuse its gather code. For EVERY new example i with old index p[i] it rebuilds
the example from both files with plain per-example slicing and compares, byte for byte:
  windows/start_sample, windows/trigger_sample; segments/{pmt, window_in_example, start_sample, length};
  segment sample offsets relative to the example start; samples; every truth/* field (row); real_pe/{label, pmt, t,
  win} slices.
Global checks: dataset set, dtype, shape, chunk shape and filters identical; offsets start at 0, are monotone and
end at the data length; file attributes identical except `subsample_json` (must be absent) and `format` (reported if
changed); p is a permutation; per-class counts and weight sums unchanged; float sums of samples / real_pe/t unchanged.
Order test (new file): class runs vs the random-order expectation, longest same-class run, Spearman(index, cls), and
the task metric of the index-only predictor (geo_score = index) - which scored 1.0 on the sorted source.
All files are opened read-only. Exit 0 only if every check passes.

usage: verify_shuffled_group.py --old-wave A.h5 --old-labels A.labels.h5 --new-wave B.h5 --new-labels B.labels.h5
                                --perm PRIVATE_permutation_*.npz [--metrics-plugin .../_obd_metrics.py]
"""
import argparse
import importlib.util
import json
import sys
import time
import types

import h5py
import numpy as np

FAIL = []


def check(ok, msg):
    if not ok:
        FAIL.append(msg)
        print("FAIL:", msg, flush=True)
    return ok


def props(ds):
    return (ds.dtype.str, ds.shape, ds.chunks, ds.compression, ds.compression_opts, ds.shuffle, ds.fletcher32,
            ds.scaleoffset, None if ds.fillvalue is None else np.asarray(ds.fillvalue).tobytes())


def compare_files(old, new, path_old, path_new):
    names_o, names_n = [], []
    old.visititems(lambda n, o: names_o.append(n) if isinstance(o, h5py.Dataset) else None)
    new.visititems(lambda n, o: names_n.append(n) if isinstance(o, h5py.Dataset) else None)
    check(sorted(names_o) == sorted(names_n), f"{path_new}: dataset set differs {sorted(set(names_o) ^ set(names_n))}")
    for k in names_o:
        if k in names_n:
            check(props(old[k]) == props(new[k]), f"{k}: properties {props(old[k])} -> {props(new[k])}")
        for kk in old[k].attrs:
            check(kk in new[k].attrs, f"{k}: object attribute {kk} lost")
    ao, an = dict(old.attrs), dict(new.attrs)
    check("subsample_json" not in an, f"{path_new}: subsample_json still present")
    for k, v in ao.items():
        if k == "subsample_json":
            continue
        if k == "format" and k in an and an[k] != v:
            print(f"note: format attribute replaced: {v!r} -> {an[k]!r}")
            continue
        check(k in an and an[k] == v, f"{path_new}: attribute {k} differs or missing")
    check(set(an) <= set(ao), f"{path_new}: new attributes {set(an) - set(ao)}")
    check(list(k for k in an) == [k for k in ao if k in an], f"{path_new}: attribute order changed")
    return names_o


def offsets_ok(off, length, name):
    check(off[0] == 0 and off[-1] == length and np.all(np.diff(off) >= 0), f"{name}: bad offsets")


def load(f, names):
    return {k: f[k][()] for k in names}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("old-wave", "old-labels", "new-wave", "new-labels", "perm"):
        ap.add_argument("--" + k, required=True)
    ap.add_argument("--metrics-plugin", default=None)
    a = ap.parse_args()
    t0 = time.perf_counter()
    p = np.load(a.perm)["new_to_old"]
    n = len(p)
    check(np.array_equal(np.sort(p), np.arange(n)), "p is not a permutation")
    with h5py.File(a.old_wave, "r") as ow, h5py.File(a.new_wave, "r") as nw:
        names = compare_files(ow, nw, a.old_wave, a.new_wave)
        O, N = load(ow, names), load(nw, names)
    print(f"waveform files loaded {time.perf_counter() - t0:.0f} s", flush=True)
    for X, tag in ((O, "old"), (N, "new")):
        offsets_ok(X["examples/win_off"], len(X["windows/start_sample"]), tag + " win_off")
        offsets_ok(X["examples/seg_off"], len(X["segments/pmt"]), tag + " seg_off")
        offsets_ok(X["segments/sample_off"], len(X["samples"]), tag + " sample_off")
        check(np.array_equal(np.diff(X["segments/sample_off"]), X["segments/length"].astype(np.int64)), tag + " sample_off vs length")
        check(len(X["examples/win_off"]) == n + 1 and len(X["examples/seg_off"]) == n + 1, tag + " example count")
    for k in names:
        check(len(O[k]) == len(N[k]), f"{k}: length {len(O[k])} -> {len(N[k])}")
    check(int(O["samples"].astype(np.int64).sum()) == int(N["samples"].astype(np.int64).sum()), "samples sum differs")
    win_k = ("windows/start_sample", "windows/trigger_sample")
    seg_k = ("segments/pmt", "segments/window_in_example", "segments/start_sample", "segments/length")
    bad = 0
    for i in range(n):
        e = int(p[i])
        ok = True
        w0o, w1o = O["examples/win_off"][e], O["examples/win_off"][e + 1]
        w0n, w1n = N["examples/win_off"][i], N["examples/win_off"][i + 1]
        for k in win_k:
            ok &= O[k][w0o:w1o].tobytes() == N[k][w0n:w1n].tobytes()
        s0o, s1o = O["examples/seg_off"][e], O["examples/seg_off"][e + 1]
        s0n, s1n = N["examples/seg_off"][i], N["examples/seg_off"][i + 1]
        for k in seg_k:
            ok &= O[k][s0o:s1o].tobytes() == N[k][s0n:s1n].tobytes()
        so_o = O["segments/sample_off"][s0o:s1o + 1]; so_n = N["segments/sample_off"][s0n:s1n + 1]
        ok &= (so_o - so_o[0]).tobytes() == (so_n - so_n[0]).tobytes()
        ok &= O["samples"][so_o[0]:so_o[-1]].tobytes() == N["samples"][so_n[0]:so_n[-1]].tobytes()
        if not ok:
            bad += 1
            if bad <= 5:
                print(f"FAIL: waveform example new {i} / old {e} differs")
    check(bad == 0, f"{bad} waveform examples differ")
    print(f"waveform: {n} examples compared, {bad} differ ({time.perf_counter() - t0:.0f} s)", flush=True)
    del O, N
    with h5py.File(a.old_labels, "r") as ol, h5py.File(a.new_labels, "r") as nl:
        names = compare_files(ol, nl, a.old_labels, a.new_labels)
        O, N = load(ol, names), load(nl, names)
    truth = [k for k in names if k.startswith("truth/")]
    for k in truth:
        check(len(N[k]) == n, f"{k}: {len(N[k])} rows")
    pe = ("real_pe/label", "real_pe/pmt", "real_pe/t", "real_pe/win")
    for X, tag in ((O, "old"), (N, "new")):
        offsets_ok(X["real_pe/off"], len(X["real_pe/pmt"]), tag + " real_pe/off")
    check(float(O["real_pe/t"].astype(np.float64).sum()) == float(N["real_pe/t"].astype(np.float64).sum()), "real_pe/t sum differs")
    bad = 0
    for i in range(n):
        e = int(p[i])
        ok = True
        for k in truth:
            ok &= O[k][e:e + 1].tobytes() == N[k][i:i + 1].tobytes()
        a0, a1 = O["real_pe/off"][e], O["real_pe/off"][e + 1]
        b0, b1 = N["real_pe/off"][i], N["real_pe/off"][i + 1]
        for k in pe:
            ok &= O[k][a0:a1].tobytes() == N[k][b0:b1].tobytes()
        if not ok:
            bad += 1
            if bad <= 5:
                print(f"FAIL: labels example new {i} / old {e} differs")
    check(bad == 0, f"{bad} label rows differ")
    print(f"labels: {n} rows compared, {bad} differ ({time.perf_counter() - t0:.0f} s)", flush=True)
    cls_o, cls_n = O["truth/cls"], N["truth/cls"]
    w_o, w_n = O["truth/weight_per_year"], N["truth/weight_per_year"]
    check(np.array_equal(np.bincount(cls_o, minlength=5), np.bincount(cls_n, minlength=5)), "class counts differ")
    for c in range(5):
        check(np.isclose(w_o[cls_o == c].sum(), w_n[cls_n == c].sum(), rtol=1e-12, atol=0), f"class {c} weight sum")
    # ---- order test on the new file
    rep = {"class_counts": np.bincount(cls_n, minlength=5).tolist()}
    for tag, c in (("old", cls_o), ("new", cls_n)):
        runs = int(np.sum(c[1:] != c[:-1]) + 1)
        b = np.flatnonzero(np.r_[True, c[1:] != c[:-1], True])
        rep[tag] = {"class_runs": runs, "longest_run": int(np.diff(b).max())}
    cnt = np.bincount(cls_n).astype(float)
    exp_runs = 1 + (n * n - np.sum(cnt ** 2)) / n                 # E[runs] for a uniformly random order
    rep["expected_runs_random"] = float(exp_runs)
    from scipy.stats import spearmanr                            # average ranks for ties
    rep["spearman_index_cls"] = {"old": float(spearmanr(np.arange(n), cls_o)[0]), "new": float(spearmanr(np.arange(n), cls_n)[0])}
    geo = np.isin(cls_n, (0, 1))
    rep["spearman_index_isgeo_new"] = float(np.corrcoef(np.arange(n), geo.astype(float))[0, 1])
    if a.metrics_plugin:
        for m in ("execute_tools", "execute_tools.evaluation_metric", "execute_tools.task_data_path"):
            sys.modules.setdefault(m, types.ModuleType(m))
        sys.modules["execute_tools.evaluation_metric"].EvaluationMetric = object
        sys.modules["execute_tools.task_data_path"].require_bound_task_data_path = lambda *x, **k: None
        spec = importlib.util.spec_from_file_location("_om", a.metrics_plugin)
        om = importlib.util.module_from_spec(spec); spec.loader.exec_module(om)
        idx = np.arange(n, dtype=float)
        rep["index_predictor_selection_sb1"] = {"old": om.selection_at(idx, cls_o, w_o), "new": om.selection_at(idx, cls_n, w_n)}
        rep["index_predictor_fom"] = {"old": om.fom_best(idx, cls_o, w_o), "new": om.fom_best(idx, cls_n, w_n)}
    print(json.dumps(rep, indent=1))
    print(f"{'PASS' if not FAIL else 'FAIL'}: {len(FAIL)} failed checks; {time.perf_counter() - t0:.0f} s")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
