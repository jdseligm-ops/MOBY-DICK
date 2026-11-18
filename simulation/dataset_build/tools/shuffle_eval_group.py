#!/usr/bin/env python3
"""Rewrite one published evaluation group file pair (<group>_NNN.h5 + <group>_NNN.labels.h5) in a SECRET random
example order (Z2 option B, advisor 2026-11-17 02:32; NOT YET APPROVED BY THE USER - prepare only).

Why: the v3e validation/test files are stored class-sorted with fixed boundaries, and their `subsample_json` attribute
lists the class counts, so the example index (part of every example id) reveals the class (Z2 report L1/L2).

What it does (sources are opened read-only, mode 'r'; outputs go to NEW paths only):
  * draws a permutation p from a secret 256-bit key (secrets.token_bytes; never a published seed): new example i is
    old example p[i]. The SAME p is applied to the waveform file and its labels file;
  * waveform file: examples/{win_off, seg_off} and segments/sample_off are rebuilt; windows/*, segments/{pmt,
    window_in_example, start_sample, length} and samples are gathered per example; every value is copied unchanged;
  * labels file: truth/* rows are permuted; real_pe/off is rebuilt and real_pe/{label, pmt, t, win} gathered;
  * every dataset keeps its dtype, shape, chunk shape and filters (gzip level, shuffle, fletcher32, scaleoffset,
    fill value) from the source; file attributes are copied byte-identical in source order EXCEPT `subsample_json`,
    which is dropped (its content minus the cluster paths goes to the public manifest). `format` is kept unless
    --format-attr is given;
  * writes the permutation, the key and the inverse to a PRIVATE npz (mode 0600; never publish it), and a public
    manifest JSON with sha256 of sources, outputs, the permutation array and this script.
Any dataset that is not in the known schema stops the run (nothing is silently dropped).
Verification: tools/verify_shuffled_group.py (independent per-example comparison).

usage: shuffle_eval_group.py --wave SRC.h5 --labels SRC.labels.h5 --out-dir NEW_DIR --private-dir PRIVATE_DIR
                             [--format-attr "..."]
"""
import argparse
import hashlib
import json
import os
import secrets
import sys
import time

import h5py
import numpy as np

WAVE_SCHEMA = {"examples/win_off", "examples/seg_off", "windows/start_sample", "windows/trigger_sample",
               "segments/pmt", "segments/window_in_example", "segments/start_sample", "segments/length",
               "segments/sample_off", "samples"}
WAVE_ORDER = ["examples/win_off", "examples/seg_off", "windows/start_sample", "windows/trigger_sample",
              "segments/pmt", "segments/window_in_example", "segments/start_sample", "segments/length",
              "segments/sample_off", "samples"]          # build_dataset._write_part creation order
DROP_ATTRS = {"subsample_json"}
SAMPLE_BLOCK = 2048                                       # examples per block when writing `samples`


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(1 << 24):
            h.update(b)
    return h.hexdigest()


def datasets_of(f):
    out = []
    f.visititems(lambda n, o: out.append(n) if isinstance(o, h5py.Dataset) else None)
    return out


def create_like(dst, name, src_ds, data=None, shape=None):
    """Create `name` in dst with the source dataset's dtype, shape, chunks and filters (data written if given)."""
    kw = dict(dtype=src_ds.dtype, shape=src_ds.shape if shape is None else shape)
    if src_ds.chunks is not None:
        kw.update(chunks=src_ds.chunks, compression=src_ds.compression, compression_opts=src_ds.compression_opts,
                  shuffle=src_ds.shuffle, fletcher32=src_ds.fletcher32)
        if src_ds.scaleoffset is not None:
            kw["scaleoffset"] = src_ds.scaleoffset
    if src_ds.fillvalue is not None:
        kw["fillvalue"] = src_ds.fillvalue
    ds = dst.create_dataset(name, **kw)
    if data is not None:
        if data.dtype != src_ds.dtype or data.shape != ds.shape:
            raise SystemExit(f"{name}: built {data.dtype}{data.shape}, source {src_ds.dtype}{ds.shape}")
        ds[...] = data
    return ds


def range_index(starts, counts):
    """Concatenated ranges [starts[k], starts[k]+counts[k]) as one int64 index array."""
    counts = np.asarray(counts, np.int64)
    total = int(counts.sum())
    first = np.concatenate(([0], np.cumsum(counts)[:-1]))
    return np.repeat(np.asarray(starts, np.int64) - first, counts) + np.arange(total, dtype=np.int64)


def offsets(counts):
    return np.concatenate(([0], np.cumsum(counts))).astype(np.int64)


def copy_attrs(src, dst, format_attr):
    kept = []
    for k, v in src.attrs.items():
        if k in DROP_ATTRS:
            continue
        if k == "format" and format_attr is not None:
            v = format_attr
        dst.attrs[k] = v
        kept.append(k)
    return kept


def shuffle_wave(src_path, dst_path, p, format_attr):
    with h5py.File(src_path, "r") as s:
        names = set(datasets_of(s))
        if names != WAVE_SCHEMA:
            raise SystemExit(f"{src_path}: datasets {sorted(names ^ WAVE_SCHEMA)} differ from the known schema")
        wo, so = s["examples/win_off"][()], s["examples/seg_off"][()]
        soff = s["segments/sample_off"][()]
        n = len(wo) - 1
        if len(p) != n:
            raise SystemExit(f"permutation length {len(p)} != {n} examples")
        nwin, nseg = np.diff(wo)[p], np.diff(so)[p]
        widx = range_index(wo[:-1][p], nwin)
        sidx = range_index(so[:-1][p], nseg)
        ex_s0, ex_s1 = soff[so[:-1]], soff[so[1:]]                 # sample range of each old example
        nsamp = (ex_s1 - ex_s0)[p]
        tmp = dst_path + ".partial"
        with h5py.File(tmp, "w") as d:
            attrs = copy_attrs(s, d, format_attr)
            built = {"examples/win_off": offsets(nwin), "examples/seg_off": offsets(nseg)}
            for k in ("windows/start_sample", "windows/trigger_sample"):
                built[k] = s[k][()][widx]
            for k in ("segments/pmt", "segments/window_in_example", "segments/start_sample", "segments/length"):
                built[k] = s[k][()][sidx]
            built["segments/sample_off"] = offsets(built["segments/length"].astype(np.int64))
            del sidx, widx
            for k in WAVE_ORDER:
                if k == "samples":
                    samples = s["samples"][()]
                    ds = create_like(d, k, s[k])
                    new_off = offsets(nsamp)
                    for b0 in range(0, n, SAMPLE_BLOCK):
                        b1 = min(n, b0 + SAMPLE_BLOCK)
                        idx = range_index(ex_s0[p[b0:b1]], nsamp[b0:b1])
                        ds[new_off[b0]:new_off[b1]] = samples[idx]
                    del samples
                else:
                    create_like(d, k, s[k], built.pop(k))
        os.chmod(tmp, 0o440)                              # read-only once written (frozen candidate)
        os.replace(tmp, dst_path)
    return {"examples": int(n), "attrs_written": attrs}


def shuffle_labels(src_path, dst_path, p):
    with h5py.File(src_path, "r") as s:
        names = datasets_of(s)
        truth = [k for k in names if k.startswith("truth/")]
        pe = {"real_pe/off", "real_pe/label", "real_pe/pmt", "real_pe/t", "real_pe/win"}
        other = set(names) - set(truth) - pe
        if other or not pe <= set(names):
            raise SystemExit(f"{src_path}: unexpected datasets {sorted(other)} or missing {sorted(pe - set(names))}")
        n = len(p)
        off = s["real_pe/off"][()]
        if len(off) != n + 1:
            raise SystemExit(f"real_pe/off has {len(off)} entries for {n} examples")
        cnt = np.diff(off)[p]
        pidx = range_index(off[:-1][p], cnt)
        tmp = dst_path + ".partial"
        with h5py.File(tmp, "w") as d:
            attrs = copy_attrs(s, d, None)
            for k in truth:
                v = s[k][()]
                if len(v) != n:
                    raise SystemExit(f"{k}: {len(v)} rows for {n} examples")
                create_like(d, k, s[k], v[p])
            create_like(d, "real_pe/off", s["real_pe/off"], offsets(cnt))
            for k in ("real_pe/label", "real_pe/pmt", "real_pe/t", "real_pe/win"):
                create_like(d, k, s[k], s[k][()][pidx])
        os.chmod(tmp, 0o440)
        os.replace(tmp, dst_path)
    return {"truth_fields": len(truth), "attrs_written": attrs}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wave", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out-dir", required=True, help="new directory for the shuffled pair (must not hold them yet)")
    ap.add_argument("--private-dir", required=True, help="directory for the PRIVATE permutation (never published)")
    ap.add_argument("--format-attr", default=None, help="replacement for the `format` attribute (default: unchanged)")
    a = ap.parse_args()
    stem = os.path.basename(a.wave)[:-3]
    if os.path.basename(a.labels) != stem + ".labels.h5":
        raise SystemExit("--labels must be the labels file of --wave")
    os.makedirs(a.out_dir, exist_ok=True)
    os.makedirs(a.private_dir, exist_ok=True)
    out_w, out_l = os.path.join(a.out_dir, stem + ".h5"), os.path.join(a.out_dir, stem + ".labels.h5")
    priv = os.path.join(a.private_dir, f"PRIVATE_permutation_{stem}_DO_NOT_PUBLISH.npz")
    for path in (out_w, out_l, priv):
        if os.path.exists(path):
            raise SystemExit(f"{path} exists; refusing to overwrite")
    srcs = {os.path.realpath(x) for x in (a.wave, a.labels)}
    if any(os.path.realpath(x) in srcs for x in (out_w, out_l)):
        raise SystemExit("output path equals a source path")
    t0 = time.perf_counter()
    with h5py.File(a.wave, "r") as f:
        n = int(f["examples/win_off"].shape[0]) - 1
        sub = f.attrs.get("subsample_json")
    key = secrets.token_bytes(32)
    p = np.random.default_rng(int.from_bytes(key, "big")).permutation(n).astype(np.int64)
    inv = np.empty_like(p); inv[p] = np.arange(n)
    np.savez(priv, new_to_old=p, old_to_new=inv, key_hex=np.array(key.hex()),
             note=np.array("new example i = old example new_to_old[i]. PRIVATE: publishing this undoes the shuffle."))
    os.chmod(priv, 0o600)
    perm_sha = hashlib.sha256(p.astype("<i8").tobytes()).hexdigest()
    t1 = time.perf_counter()
    rw = shuffle_wave(a.wave, out_w, p, a.format_attr)
    t2 = time.perf_counter()
    rl = shuffle_labels(a.labels, out_l, p)
    t3 = time.perf_counter()
    dropped = None
    if sub is not None:
        dropped = json.loads(sub)
        dropped.pop("source", None)                       # cluster paths (privacy, rule 16)
    manifest = {
        "group_file": stem, "examples": n, "script": os.path.basename(__file__), "script_sha256": sha256_file(__file__),
        "source_sha256": {os.path.basename(a.wave): sha256_file(a.wave), os.path.basename(a.labels): sha256_file(a.labels)},
        "output_sha256": {os.path.basename(out_w): sha256_file(out_w), os.path.basename(out_l): sha256_file(out_l)},
        "output_bytes": {os.path.basename(out_w): os.path.getsize(out_w), os.path.basename(out_l): os.path.getsize(out_l)},
        "permutation_sha256_int64_le_new_to_old": perm_sha,
        "permutation_rule": "secret 256-bit key from secrets.token_bytes -> numpy default_rng(key).permutation(n); "
                            "key and mapping kept privately (not published)",
        "dropped_attribute_subsample_json_without_source_paths": dropped,
        "format_attr_replaced": a.format_attr is not None,
        "wave": rw, "labels": rl,
        "seconds": {"permutation": round(t1 - t0, 2), "waveform": round(t2 - t1, 1), "labels": round(t3 - t2, 1),
                    "total_incl_hashing": round(time.perf_counter() - t0, 1)},
        "argv": [os.path.basename(x) for x in sys.argv],   # basenames only (no local paths)
    }
    with open(os.path.join(a.out_dir, f"{stem}.shuffle_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print(json.dumps({k: manifest[k] for k in ("group_file", "examples", "output_sha256", "seconds")}, indent=1))


if __name__ == "__main__":
    main()
