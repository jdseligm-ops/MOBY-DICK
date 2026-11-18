#!/usr/bin/env python3
"""Write manifest.json (name, size, md5 of every final file) and plans.json (the accidental pair plans of every shard:
strata, empty bins, draws) for a dataset build folder.  usage: dataset_manifest.py <dataset build dir>"""
import glob, hashlib, json, os, sys
import h5py
D = sys.argv[1]
man = []
for f in sorted(glob.glob(os.path.join(D, "final", "*.h5"))):
    h = hashlib.md5()
    with open(f, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 24), b""):
            h.update(b)
    man.append({"name": os.path.basename(f), "size": os.path.getsize(f), "md5": h.hexdigest()})
json.dump(man, open(os.path.join(D, "final", "manifest.json"), "w"), indent=1)
plans = {}
for f in sorted(glob.glob(os.path.join(D, "shards", "acc_*.h5"))):
    m = json.loads(h5py.File(f, "r").attrs["meta_json"])
    for p in m["plan"]:
        key = f"{m['split']}|{p['i']}|{p['j']}"
        plans.setdefault(key, {k: p[k] for k in p if k not in ("M_ij",)} | {"M_ij": p["M_ij"], "shards": 0})
        plans[key]["shards"] += 1
json.dump(plans, open(os.path.join(D, "final", "plans.json"), "w"), indent=1)
print("MANIFEST_DONE", len(man), "files;", len(plans), "plans; empty-bin plans:", sum(1 for p in plans.values() if p.get("empty_split_bins_with_true_rate")))
