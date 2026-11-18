#!/usr/bin/env python3
"""MOBY-DICK: one entry point for the OBD 17 kt geoneutrino IBD baseline (model v3r).

    python run.py setup                      create ./.venv and install the pinned packages (done automatically on first use)
    python run.py demo                       run the model on the bundled 200-example sample (no download needed)
    python run.py fetch    [--groups geometry,val]      download + md5-verify the dataset from Zenodo into ./data
    python run.py predict  --input FILE_OR_DIR          predictions for any waveform files (no labels needed)
    python run.py evaluate [--data_dir data]            the 9 task metrics on the validation files (needs labels)
    python run.py evaluate --predictions P.json         metrics of an existing predictions file (no model run)
    python run.py train    [--data_dir data] --yes      retrain from the train files (seed 20261114)

Requirements: Python 3.11-3.14 (3.12.3 tested) on Linux x86_64 (tested); macOS best effort; Windows untested.
Internet once, for `setup` (PyPI) and `fetch` (Zenodo). Nothing else: no SIDERIUS framework, no compiler, no admin
rights. `setup` makes ./.venv with the standard-library venv module, bootstraps a hash-checked pip wheel, and installs
requirements.lock with `pip --require-hashes --only-binary=:all: --no-deps` (numpy 2.4.3, scipy 1.17.1, h5py 3.16.0,
scikit-learn 1.9.1, skops 0.13.0 and their dependencies: the versions that produced the shipped results).

Every subcommand except `setup` and `fetch` re-runs itself inside ./.venv. baseline/ is used unchanged; only the
task metrics come from obd_runner/metrics.py instead of the SIDERIUS task package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.dont_write_bytecode = True                             # keep the checkout clean (no __pycache__ in baseline/)
ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
LOCK = ROOT / "requirements.lock"
STAMP = VENV / ".moby_dick_lock_sha256"
BASELINE = ROOT / "baseline"
MODEL = BASELINE / "final_model.skops"
DEMO = ROOT / "demo"
PIP_WHEEL = ("https://files.pythonhosted.org/packages/44/3c/d717024885424591d5376220b5e836c2d5293ce2011523c9de23ff7bf068/"
             "pip-25.3-py3-none-any.whl", "9655943313a94722b7774661c21049070f6bbb0a1516bf02f7c8d5d9201514cd")
SEED = 20261114
PY_OK = ((3, 11), (3, 14))


# ------------------------------------------------------------------------------------------- environment (stdlib only)
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def in_venv() -> bool:
    return Path(sys.prefix).resolve() == VENV.resolve()


def venv_ready() -> bool:
    return venv_python().exists() and STAMP.exists() and STAMP.read_text().strip() == _sha256(LOCK)


def setup(force: bool = False) -> None:
    if not (PY_OK[0] <= sys.version_info[:2] <= PY_OK[1]):
        raise SystemExit(f"Python {sys.version.split()[0]} found; this needs Python 3.11-3.14 (the pinned numpy/scipy/"
                         "scikit-learn wheels exist only for those). Run run.py with such an interpreter.")
    if venv_ready() and not force:
        print(f"environment ready: {VENV}")
        return
    t0 = time.perf_counter()
    if VENV.exists():
        shutil.rmtree(VENV)
    print(f"[setup] creating {VENV} with {sys.executable} (Python {sys.version.split()[0]})", flush=True)
    # --without-pip: works even where ensurepip is missing (e.g. Debian/Ubuntu without python3-venv's pip)
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(VENV)], check=True)
    wheel = VENV / PIP_WHEEL[0].rsplit("/", 1)[1]
    print("[setup] downloading the pinned pip wheel (sha256-checked)", flush=True)
    req = urllib.request.Request(PIP_WHEEL[0], headers={"User-Agent": "moby-dick-run/1"})
    with urllib.request.urlopen(req, timeout=120) as r, wheel.open("wb") as f:
        shutil.copyfileobj(r, f)
    if _sha256(wheel) != PIP_WHEEL[1]:
        wheel.unlink()
        raise SystemExit("[setup] the pip wheel's sha256 does not match the pinned value; refusing to continue")
    print("[setup] installing requirements.lock (hash-checked binary wheels only)", flush=True)
    py = str(venv_python())
    subprocess.run([py, str(wheel / "pip"), "install", "--disable-pip-version-check", "--no-input", "--no-cache-dir",
                    "--require-hashes", "--only-binary=:all:", "--no-deps", "-r", str(LOCK)], check=True)
    out = subprocess.run([py, "-c", "import numpy, scipy, h5py, sklearn, skops, threadpoolctl; "
                          "print(numpy.__version__, scipy.__version__, h5py.__version__, sklearn.__version__, skops.__version__)"],
                         check=True, capture_output=True, text=True).stdout.split()
    print(f"[setup] numpy {out[0]}, scipy {out[1]}, h5py {out[2]}, scikit-learn {out[3]}, skops {out[4]}")
    STAMP.write_text(_sha256(LOCK) + "\n")
    print(f"[setup] done in {time.perf_counter() - t0:.0f} s")


def reexec_in_venv() -> None:
    """Run this same command again with ./.venv's interpreter (creating the environment first if needed)."""
    if in_venv():
        return
    if not venv_ready():
        print("first use: setting up the environment (one time, needs internet)", flush=True)
        setup()
    py = str(venv_python())
    args = [py, str(Path(__file__).resolve()), *sys.argv[1:]]
    sys.stdout.flush(); sys.stderr.flush()               # execv discards unflushed output
    if os.name == "nt":
        raise SystemExit(subprocess.run(args).returncode)
    os.execv(py, args)


# ------------------------------------------------------------------------------------------- model work (inside .venv)
def _procs(n):
    if n:
        return n
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:
        return os.cpu_count() or 1


def _baseline():
    sys.path.insert(0, str(BASELINE))
    sys.dont_write_bytecode = True                         # keep baseline/ byte-identical (no __pycache__)
    import run_baseline as rb
    from obd_runner import metrics as om
    rb.task_metrics = om.task_metrics                      # the only two SIDERIUS-dependent functions
    rb.bootstrap = om.bootstrap
    return rb


def _geometry(explicit, *folders):
    for c in ([Path(explicit)] if explicit else []) + [Path(f) / "pmt_geometry.h5" for f in folders]:
        if c.is_file():
            return str(c)
    raise SystemExit("no pmt_geometry.h5 found; pass --geometry")


def _waveform_files(inp: Path):
    if inp.is_file():
        return [str(inp)]
    files = sorted(str(p) for p in inp.glob("*.h5") if not p.name.endswith(".labels.h5") and p.name != "pmt_geometry.h5")
    if not files:
        raise SystemExit(f"no waveform .h5 files in {inp}")
    return files


def predict(inp, geometry, out_dir, procs, model, export=False, quiet=False):
    rb = _baseline()
    inp = Path(inp)
    files = _waveform_files(inp)
    if any(Path(f).name.startswith("test_") for f in files) and not quiet:
        print("note: predicting on test waveforms; never use test results to tune anything")
    geo = _geometry(geometry, inp if inp.is_dir() else inp.parent, ROOT / "data", DEMO)
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.perf_counter()
    rb._G = rb.oc.Geometry(geo)
    rb._M = rb.load_model(str(model))
    items, F4, PF, CF, SV, PX, SH = rb.run_chain(files, procs)
    F = rb.oc.stage4_matrix(F4, PX, rb._M)
    preds = rb.predictions(rb._M, items, F, PF, CF)
    path = os.path.join(out_dir, "predictions.json")
    with open(path, "w") as f:
        json.dump(preds, f)
    dt = time.perf_counter() - t0
    if export:
        rb._M["want_std"] = True
        rb.export(rb._M, os.path.dirname(files[0]), [os.path.basename(f) for f in files], out_dir, procs)
    print(f"predicted {len(preds)} examples from {len(files)} file(s) in {dt:.1f} s ({procs} processes) -> {path}")
    print("format: {\"<file stem>:<6-digit index>\": [geo_score, prompt x, y, z, capture x, y, z]} (metres); "
          "geo_score < 0 = failed the physical preselection")
    return preds, path


def evaluate(a):
    from obd_runner import metrics as om
    data_dir = os.path.abspath(a.data_dir)
    os.makedirs(a.output_dir, exist_ok=True)
    t0 = time.perf_counter()
    if a.predictions:                                      # metrics of an existing predictions file
        with open(a.predictions) as f:
            preds = json.load(f)
        met, truth = om.task_metrics(a.predictions, preds, data_dir)
        if a.bootstrap:
            with open(os.path.join(a.output_dir, "metrics_bootstrap.json"), "w") as f:
                json.dump(om.bootstrap(preds, truth, a.bootstrap, SEED), f, indent=1, sort_keys=True)
    else:                                                  # run the model on the val files, as run_baseline.py evaluate
        rb = _baseline()
        rb.HP["bootstrap_resamples"] = a.bootstrap or rb.HP["bootstrap_resamples"]
        rb._G = rb.oc.Geometry(os.path.join(data_dir, "pmt_geometry.h5"))
        rb._M = rb.load_model(str(a.model))
        log = {"cmd": "evaluate", "procs": a.procs, "metrics_source": "obd_runner/metrics.py"}
        met = rb.evaluate(rb._M, data_dir, a.output_dir, a.procs, log)
        log["total_s"] = time.perf_counter() - t0
        with open(os.path.join(a.output_dir, "evaluate_log.json"), "w") as f:
            json.dump(log, f, indent=1)
    with open(os.path.join(a.output_dir, "metrics.json"), "w") as f:
        json.dump(met, f, indent=1, sort_keys=True)
    print(json.dumps(met, indent=1, sort_keys=True))
    print(f"evaluate: {time.perf_counter() - t0:.1f} s -> {a.output_dir}/metrics.json")


def train(a):
    if not a.yes:
        raise SystemExit("train retrains the whole chain from the 7 train files (~20 GB in --data_dir): about 12 min on "
                         "20 cores in the recorded run (peak memory not recorded). Add --yes to start.")
    rb = _baseline()
    data_dir = os.path.abspath(a.data_dir)
    os.makedirs(a.output_dir, exist_ok=True)
    t0 = time.perf_counter()
    log = {"cmd": "train", "procs": a.procs, "seed": a.seed, "hp": rb.HP, "metrics_source": "obd_runner/metrics.py"}
    path = rb.train(data_dir, a.seed, a.output_dir, a.procs, log)
    rb._M = rb.load_model(path)                            # evaluate exactly what was saved
    if not a.skip_evaluate:
        rb._G = rb.oc.Geometry(os.path.join(data_dir, "pmt_geometry.h5"))
        met = rb.evaluate(rb._M, data_dir, a.output_dir, a.procs, log)
        print(json.dumps(met, indent=1, sort_keys=True))
    log["total_s"] = time.perf_counter() - t0
    with open(os.path.join(a.output_dir, "train_log.json"), "w") as f:
        json.dump(log, f, indent=1, default=str)
    print(f"train: {log['total_s']:.0f} s -> {path}")


def demo(a):
    sample = DEMO / "demo_000.h5"
    if not sample.is_file():
        raise SystemExit(f"{sample} is missing")
    preds, path = predict(sample, str(DEMO / "pmt_geometry.h5"), a.output_dir, a.procs, MODEL, quiet=True)
    keys = sorted(preds)
    passed = sum(preds[k][0] >= 0 for k in keys)
    print(f"\n{passed} of {len(keys)} examples pass the physical preselection. First rows:")
    for k in keys[:5]:
        v = preds[k]
        print(f"  {k}  geo_score {v[0]:+.3f}  prompt ({v[1]:+.2f}, {v[2]:+.2f}, {v[3]:+.2f}) m")
    print("\nThis demo shows that the model runs; it claims no score. 200 examples cannot resolve the task metrics "
          "(the S/B = 1 selection needs the full 49,000-example validation file: `python run.py fetch` then "
          "`python run.py evaluate`).")


# ------------------------------------------------------------------------------------------- command line
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("setup", help="create ./.venv and install requirements.lock (automatic on first use)")
    s.add_argument("--force", action="store_true", help="rebuild the environment")
    f = sp.add_parser("fetch", help="download + md5-verify the dataset from Zenodo (works once the record is published)")
    f.add_argument("--data_dir", default=str(ROOT / "data"))
    f.add_argument("--groups", default="geometry,val",
                   help="comma list of geometry, val (3.2 GB), train (20 GB), test (waveforms only, 2.9 GB); default geometry,val")
    f.add_argument("--source_dir", help="copy from a folder that already holds the Zenodo files instead of downloading")
    p = sp.add_parser("predict", help="predictions for any waveform files")
    p.add_argument("--input", required=True, help="a waveform .h5 file or a folder of them")
    p.add_argument("--geometry", help="pmt_geometry.h5 (default: next to the input, then ./data, then demo/)")
    p.add_argument("--output_dir", default=str(ROOT / "outputs" / "predict"))
    p.add_argument("--export", action="store_true", help="also write <file>.chain.npz (features, conventional fits)")
    e = sp.add_parser("evaluate", help="the 9 task metrics on the validation files in --data_dir")
    e.add_argument("--data_dir", default=str(ROOT / "data"))
    e.add_argument("--predictions", help="score this predictions.json instead of running the model")
    e.add_argument("--output_dir", default=str(ROOT / "outputs" / "evaluate"))
    e.add_argument("--bootstrap", type=int, default=0, help="bootstrap resamples (model run default 200; with --predictions 0)")
    t = sp.add_parser("train", help="retrain the chain from the train files")
    t.add_argument("--data_dir", default=str(ROOT / "data"))
    t.add_argument("--seed", type=int, default=SEED)
    t.add_argument("--output_dir", default=str(ROOT / "outputs" / "train"))
    t.add_argument("--skip_evaluate", action="store_true", help="do not evaluate on the val files afterwards")
    t.add_argument("--yes", action="store_true", help="confirm the long run")
    d = sp.add_parser("demo", help="predict on the bundled 200-example sample (no download)")
    d.add_argument("--output_dir", default=str(ROOT / "outputs" / "demo"))
    for q in (p, e, t, d):
        q.add_argument("--procs", type=int, default=0, help="worker processes (default: all cores)")
    for q in (p, e):
        q.add_argument("--model", default=str(MODEL))
    a = ap.parse_args()

    if a.cmd == "setup":
        setup(a.force)
        return
    if a.cmd == "fetch":                                   # standard library only: no environment needed
        sys.path.insert(0, str(ROOT))
        from obd_runner.fetch import GROUPS, fetch
        groups = {g.strip() for g in a.groups.split(",") if g.strip()}
        if groups - set(GROUPS):
            raise SystemExit(f"unknown group(s) {sorted(groups - set(GROUPS))}; choose from {GROUPS}")
        raise SystemExit(fetch(a.data_dir, groups, a.source_dir))
    reexec_in_venv()
    sys.path.insert(0, str(ROOT))
    a.procs = _procs(a.procs)
    if a.cmd == "predict":
        predict(a.input, a.geometry, a.output_dir, a.procs, a.model, a.export)
    elif a.cmd == "evaluate":
        evaluate(a)
    elif a.cmd == "train":
        train(a)
    elif a.cmd == "demo":
        demo(a)


if __name__ == "__main__":
    main()
