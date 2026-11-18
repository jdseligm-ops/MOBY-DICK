"""Cut the first N examples of a published waveform file (and its labels file) into a small file with the same layout.

    python -m obd_runner.cut_sample --wave val_000.h5 --labels val_000.labels.h5 --n 200 --out demo/demo_000

The published files are stored in random order, so the first N examples are a random sample. Used to make demo/.
"""
import argparse
import json

import h5py
import numpy as np


def _ds(dst, name, data, gz):
    kw = {"compression": "gzip", "compression_opts": 4, "chunks": True} if gz and len(data) else {}
    dst.create_dataset(name, data=data, **kw)


def cut(wave, labels, n, out):
    with h5py.File(wave, "r") as f, h5py.File(out + ".h5", "w") as g:
        for k, v in f.attrs.items():
            g.attrs[k] = v
        wo, so = f["examples/win_off"][: n + 1], f["examples/seg_off"][: n + 1]
        s0, s1 = int(so[0]), int(so[-1])
        soff = f["segments/sample_off"][s0: s1 + 1]
        _ds(g, "examples/win_off", wo - wo[0], False)
        _ds(g, "examples/seg_off", so - so[0], False)
        for k in ("start_sample", "trigger_sample"):
            _ds(g, f"windows/{k}", f[f"windows/{k}"][wo[0]: wo[-1]], False)
        for k in ("length", "pmt", "start_sample", "window_in_example"):
            _ds(g, f"segments/{k}", f[f"segments/{k}"][s0:s1], False)
        _ds(g, "segments/sample_off", soff - soff[0], False)
        _ds(g, "samples", f["samples"][int(soff[0]): int(soff[-1])], True)
    with h5py.File(labels, "r") as f, h5py.File(out + ".labels.h5", "w") as g:
        for k in f["truth"]:
            _ds(g, f"truth/{k}", f[f"truth/{k}"][:n], False)
        po = f["real_pe/off"][: n + 1]
        _ds(g, "real_pe/off", po - po[0], False)
        for k in ("label", "pmt", "t", "win"):
            _ds(g, f"real_pe/{k}", f[f"real_pe/{k}"][int(po[0]): int(po[-1])], True)
    print(json.dumps({"out": out, "examples": n}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wave", required=True); ap.add_argument("--labels", required=True)
    ap.add_argument("--n", type=int, default=200); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cut(a.wave, a.labels, a.n, a.out)
