"""Standalone task metrics for the OBD 17 kt geoneutrino IBD task (no SIDERIUS framework needed).

run.py uses this module instead of the SIDERIUS task package that baseline/run_baseline.py imports in
task_metrics() and bootstrap(). The arithmetic block below (SIGNAL_CLASSES ... score_components) is a verbatim
copy of the task's metric plugin (task/plugins/_obd_metrics.py of the SIDERIUS task package, lines 45-210); only the
framework glue (EvaluationMetric classes, the bound task data path) is replaced by plain functions that read the
truth exactly as the task's data path does (plugins/_obd_task.py: read_truth_table, Obd17ktTaskDataPath.truth_table).

Metric definitions (declared ids):
  obd_combined = 0.5 * selection + 0.5 * position                       (primary)
  obd_selection_efficiency          weighted geo-IBD efficiency at weighted (alpha,n)+accidental = signal (S/B = 1)
  obd_position_score                clip(1 - mean(median prompt error, median capture error) / 2 m, 0, 1)
  obd_median_prompt_error_m, obd_median_capture_error_m
  obd_combined_val_wedge            obd_combined on the val_wedge examples only
  obd_selection_efficiency_sb0p1    efficiency at S/B = 0.1
  obd_accidentals_at_90pct_signal   accidental examples (unweighted) passing the cut that keeps 90 % of the signal
  obd_fom_best                      max S/sqrt(S+B) / sqrt(S_total)
"""

from __future__ import annotations

import glob
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import h5py
import numpy as np

METRIC_IDS = ("obd_combined", "obd_selection_efficiency", "obd_position_score", "obd_median_prompt_error_m",
              "obd_median_capture_error_m", "obd_combined_val_wedge", "obd_selection_efficiency_sb0p1",
              "obd_accidentals_at_90pct_signal", "obd_fom_best")
VALIDATION_GLOB = "val_[0-9][0-9][0-9].h5"

# ---------------------------------------------------------------- verbatim copy of the task plugin's arithmetic
SIGNAL_CLASSES = (0, 1)
BACKGROUND_CLASSES = (3, 4)
ACCIDENTAL_CLASS = 4
LOOSE_BACKGROUND_RATIO = 10.0  # secondary operating point: weighted background = 10 x signal (S/B = 0.1)
ACCIDENTAL_COUNT_EFFICIENCY = 0.9  # secondary: accidental examples passing the cut that keeps 90 % of signal
POSITION_SCALE_M = 2.0
WEDGE_SPLIT = "val_wedge"


# -- pure arithmetic (numpy only; also used by the offline test) -----------------


def _score_groups(score: np.ndarray, cls: np.ndarray, weight: np.ndarray):
    """Tie groups in descending score order: per-group signal weight, background weight, accidental count."""
    score = np.asarray(score, dtype=np.float64)
    cls = np.asarray(cls)
    weight = np.asarray(weight, dtype=np.float64)
    sig = np.isin(cls, SIGNAL_CLASSES)
    bkg = np.isin(cls, BACKGROUND_CLASSES)
    signal_total = float(weight[sig].sum())
    if not signal_total > 0.0:
        raise ValueError("selection needs geoneutrino IBD examples with positive weight")
    use = sig | bkg
    s = np.where(np.isfinite(score[use]), score[use], -np.inf)  # missing / non-finite ranks last
    levels, inverse = np.unique(-s, return_inverse=True)  # ascending -score = descending score
    n = len(levels)
    group_sig = np.bincount(inverse, weights=np.where(sig[use], weight[use], 0.0), minlength=n)
    group_bkg = np.bincount(inverse, weights=np.where(bkg[use], weight[use], 0.0), minlength=n)
    group_acc = np.bincount(inverse, weights=(cls[use] == ACCIDENTAL_CLASS).astype(np.float64), minlength=n)
    return signal_total, group_sig, group_bkg, group_acc


def _before(x: np.ndarray) -> np.ndarray:
    return np.concatenate(([0.0], np.cumsum(x)[:-1]))


def selection_at(score: np.ndarray, cls: np.ndarray, weight: np.ndarray, background_ratio: float = 1.0) -> float:
    """Weighted geoneutrino efficiency at the cut where weighted background == ``background_ratio`` x signal.

    Examples with equal scores form one tie group; the group that crosses the
    background budget is accepted fractionally (the expected value under
    random tie-breaking).
    """
    if not background_ratio > 0.0:
        raise ValueError(f"background_ratio must be positive; got {background_ratio}")
    signal_total, group_sig, group_bkg, _ = _score_groups(score, cls, weight)
    budget = background_ratio * signal_total
    bkg_before, sig_before = _before(group_bkg), _before(group_sig)
    over = np.flatnonzero(bkg_before + group_bkg > budget)
    if len(over) == 0:
        accepted = float(group_sig.sum())
    else:
        k = int(over[0])
        accepted = float(sig_before[k] + (budget - bkg_before[k]) / group_bkg[k] * group_sig[k])
    return float(np.clip(accepted / signal_total, 0.0, 1.0))


def accidentals_at_signal_efficiency(
    score: np.ndarray, cls: np.ndarray, weight: np.ndarray, efficiency: float = ACCIDENTAL_COUNT_EFFICIENCY
) -> float:
    """Accidental EXAMPLES (unweighted) accepted by the cut that keeps ``efficiency`` of the weighted signal.

    Unweighted on purpose: it counts how many distinct accidental pairs a model
    fails to reject, independent of their importance weights, so it stays
    resolved where the weighted S/B = 1 term is decided by one heavy pair. The
    tie group that reaches the signal target is accepted fractionally. 0 for a
    perfect ranking; ``efficiency`` x (number of accidentals) for a constant score.
    """
    if not 0.0 < efficiency <= 1.0:
        raise ValueError(f"efficiency must be in (0, 1]; got {efficiency}")
    signal_total, group_sig, _, group_acc = _score_groups(score, cls, weight)
    target = efficiency * signal_total
    sig_before, acc_before = _before(group_sig), _before(group_acc)
    reach = np.flatnonzero(sig_before + group_sig >= target * (1.0 - 1e-12))
    k = int(reach[0])
    fraction = (target - sig_before[k]) / group_sig[k] if group_sig[k] > 0 else 0.0
    return float(acc_before[k] + fraction * group_acc[k])


def fom_best(score: np.ndarray, cls: np.ndarray, weight: np.ndarray) -> float:
    """Best figure of merit max_cut S / sqrt(S + B), normalised by sqrt(S_total).

    S and B are the weighted geoneutrino signal and (alpha,n) + accidental
    background accepted by a cut, evaluated at tie-group boundaries only (a tie
    group is never split). Dividing by sqrt(S_total) makes it independent of the
    evaluated exposure: 1 for a perfect selection, sqrt(S_tot / (S_tot + B_tot))
    for a constant score. This is the statistical power of the geoneutrino rate
    measurement at the best cut (KamLAND chooses its likelihood-ratio cut by such
    a figure of merit). Coarse where few background examples set the optimum.
    """
    signal_total, group_sig, group_bkg, _ = _score_groups(score, cls, weight)
    s_cum, b_cum = np.cumsum(group_sig), np.cumsum(group_bkg)
    denom = np.sqrt(s_cum + b_cum)
    fom = np.divide(s_cum, denom, out=np.zeros_like(s_cum), where=denom > 0)
    return float(np.clip(fom.max() / np.sqrt(signal_total), 0.0, 1.0))


def selection_efficiency(score: np.ndarray, cls: np.ndarray, weight: np.ndarray) -> float:
    """Weighted signal efficiency at the cut where background weight == signal weight (S/B = 1)."""
    return selection_at(score, cls, weight, 1.0)


def _median_error(pred: np.ndarray, true: np.ndarray) -> float:
    ok = np.all(np.isfinite(true), axis=1)
    if not ok.any():
        raise ValueError("no geoneutrino IBD example has a finite true point")
    err = np.linalg.norm(pred[ok] - true[ok], axis=1)
    err = np.where(np.isfinite(err), err, np.inf)
    return float(np.median(err))


def position_errors(
    pred_prompt: np.ndarray, pred_capture: np.ndarray, truth: Mapping[str, Any], signal: np.ndarray
) -> tuple[float, float]:
    """Median 3-D errors (m) of the prompt vertex and the capture point on geo IBDs."""
    if not signal.any():
        raise ValueError("position errors need at least one geoneutrino IBD example")
    return (
        _median_error(pred_prompt[signal], truth["prompt_m"][signal]),
        _median_error(pred_capture[signal], truth["capture_m"][signal]),
    )


def position_term(median_prompt_m: float, median_capture_m: float) -> float:
    mean = 0.5 * (median_prompt_m + median_capture_m)
    if not np.isfinite(mean):
        return 0.0
    return float(np.clip(1.0 - mean / POSITION_SCALE_M, 0.0, 1.0))


def align_predictions(payload: Mapping[str, Any], ids: list[str]) -> np.ndarray:
    """``float64 [n, 7]`` predictions in truth order; a missing example is all-NaN."""
    out = np.full((len(ids), 7), np.nan, dtype=np.float64)
    for row, example_id in enumerate(ids):
        value = payload.get(example_id)
        if value is None:
            continue
        array = np.asarray(value, dtype=np.float64).reshape(-1)
        if array.shape == (7,):
            out[row] = array
    return out


def score_components(payload: Mapping[str, Any], truth: Mapping[str, Any], mask: np.ndarray | None = None) -> dict[str, float]:
    """Every metric value of this task for the examples in ``mask`` (all when None)."""
    pred = align_predictions(payload, list(truth["ids"]))
    cls = np.asarray(truth["cls"])
    weight = np.asarray(truth["weight"], dtype=np.float64)
    keep = np.ones(len(cls), dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    sub = {"prompt_m": np.asarray(truth["prompt_m"])[keep], "capture_m": np.asarray(truth["capture_m"])[keep]}
    signal = np.isin(cls[keep], SIGNAL_CLASSES)
    selection = selection_at(pred[keep, 0], cls[keep], weight[keep], 1.0)
    selection_loose = selection_at(pred[keep, 0], cls[keep], weight[keep], LOOSE_BACKGROUND_RATIO)
    accidentals = accidentals_at_signal_efficiency(pred[keep, 0], cls[keep], weight[keep])
    prompt_err, capture_err = position_errors(pred[keep, 1:4], pred[keep, 4:7], sub, signal)
    position = position_term(prompt_err, capture_err)
    return {
        "obd_combined": 0.5 * selection + 0.5 * position,
        "obd_selection_efficiency": selection,
        "obd_position_score": position,
        "obd_median_prompt_error_m": prompt_err,
        "obd_median_capture_error_m": capture_err,
        "obd_selection_efficiency_sb0p1": selection_loose,
        "obd_accidentals_at_90pct_signal": accidentals,
        "obd_fom_best": fom_best(pred[keep, 0], cls[keep], weight[keep]),
    }


# ---------------------------------------------------------------- truth, read as the task's data path reads it
def read_truth_table(path: str) -> dict[str, np.ndarray]:
    with h5py.File(path, "r") as f:
        t = f["truth"]
        cls = t["cls"][:].astype(np.int64)
        weight = t["weight_per_year"][:].astype(np.float64)
        prompt = np.stack([t[f"prompt_{a}"][:] for a in "xyz"], axis=1).astype(np.float64) / 1000.0
        capture = np.stack([t[f"delayed_{a}"][:] for a in "xyz"], axis=1).astype(np.float64) / 1000.0
        split = np.asarray([s.decode() if isinstance(s, bytes) else str(s) for s in t["split"][:]])
    n = len(cls)
    if not (n >= 1 and all(len(a) == n for a in (weight, prompt, capture, split))):
        raise ValueError(f"{path}: empty or inconsistent truth arrays")
    if not np.all(np.isin(cls, (0, 1, 2, 3, 4))) or not np.all(np.isfinite(weight) & (weight >= 0)):
        raise ValueError(f"{path}: truth/cls outside 0..4 or invalid weight_per_year")
    return {"cls": cls, "weight": weight, "prompt_m": prompt, "capture_m": capture, "split": split}


def group_files(data_dir: str, pattern: str = VALIDATION_GLOB) -> list[str]:
    """Waveform files of a group (sorted names), each with its labels file."""
    names = sorted(os.path.basename(p) for p in glob.glob(os.path.join(glob.escape(data_dir), pattern))
                   if not p.endswith(".labels.h5") and os.path.isfile(p))
    if not names:
        raise SystemExit(f"no files match {pattern!r} in {data_dir}")
    for name in names:
        if not os.path.isfile(os.path.join(data_dir, Path(name).stem + ".labels.h5")):
            raise SystemExit(f"{name} has no labels file in {data_dir}")
    return names


def truth_table(data_dir: str, pattern: str = VALIDATION_GLOB) -> dict[str, Any]:
    """Truth of every example of the group, in dataset order (file name, index); ids '<file stem>:<6-digit index>'."""
    parts: dict[str, list[np.ndarray]] = {k: [] for k in ("cls", "weight", "prompt_m", "capture_m", "split")}
    ids: list[str] = []
    for name in group_files(data_dir, pattern):
        t = read_truth_table(os.path.join(data_dir, Path(name).stem + ".labels.h5"))
        with h5py.File(os.path.join(data_dir, name), "r") as f:
            n_wave = int(f["examples/win_off"].shape[0]) - 1
        if n_wave != len(t["cls"]):
            raise SystemExit(f"{name} holds {n_wave} examples but its labels file holds {len(t['cls'])}")
        for k in parts:
            parts[k].append(t[k])
        ids += [f"{Path(name).stem}:{i:06d}" for i in range(n_wave)]
    table: dict[str, Any] = {k: np.concatenate(v) for k, v in parts.items()}
    table["ids"] = ids
    return table


def all_metrics(preds: Mapping[str, Any], truth: Mapping[str, Any]) -> dict[str, float]:
    """The 9 declared metrics, as the task's metric classes compute them."""
    comp = score_components(preds, truth)
    wedge = np.asarray(truth["split"]) == WEDGE_SPLIT
    if not wedge.any():
        raise ValueError(f"the evaluated examples contain no {WEDGE_SPLIT!r} examples")
    comp["obd_combined_val_wedge"] = score_components(preds, truth, wedge)["obd_combined"]
    out = {}
    for k in METRIC_IDS:
        v = float(comp[k])
        if not np.isfinite(v):
            raise SystemExit(f"metric {k} is not scoreable: {v}")
        out[k] = v
    return out


# ---------------------------------------------------------------- drop-in replacements for run_baseline.py
def task_metrics(pred_path, preds, data_dir):
    """Replacement for run_baseline.task_metrics (same signature and return value), without SIDERIUS."""
    truth = truth_table(data_dir)
    missing = [i for i in truth["ids"] if i not in preds]
    if missing:
        raise SystemExit(f"{len(missing)} evaluation examples have no prediction (e.g. {missing[:3]})")
    return all_metrics(preds, truth), truth


def bootstrap(preds, truth, n_boot, seed):
    """Replacement for run_baseline.bootstrap: the same resampling (same RNG calls) scored by score_components above."""
    T = {k: np.asarray(truth[k]) for k in ("ids", "cls", "weight", "prompt_m", "capture_m", "split")}
    rng = np.random.default_rng([seed, 99])
    draws: dict[str, list[float]] = {}
    for _ in range(n_boot):
        idx = np.concatenate([rng.choice(np.flatnonzero(T["cls"] == c), (T["cls"] == c).sum(), replace=True) for c in np.unique(T["cls"])])
        sub = {k: v[idx] for k, v in T.items()}
        sub["ids"] = list(sub["ids"])
        comp = score_components(preds, sub)
        wedge = sub["split"] == WEDGE_SPLIT
        comp["obd_combined_val_wedge"] = score_components(preds, sub, wedge)["obd_combined"] if wedge.any() else float("nan")
        for k, v in comp.items():
            draws.setdefault(k, []).append(v)
    return {k: {"q2.5": float(np.nanquantile(v, 0.025)), "q16": float(np.nanquantile(v, 0.16)), "median": float(np.nanmedian(v)),
                "q84": float(np.nanquantile(v, 0.84)), "q97.5": float(np.nanquantile(v, 0.975))} for k, v in draws.items()} | {"n_boot": n_boot}
