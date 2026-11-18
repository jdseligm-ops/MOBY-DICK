# MOBY-DICK: compact geoneutrino IBD selection and vertex baseline for a 17 kt Ocean Bottom Detector

This repository holds the shipped baseline model (version **v3r**) of the SIDERIUS Track 1 task "OBD 17 kt geoneutrino IBD selection and vertex reconstruction", together with the code that trains and runs it.

## What the model does

The input is simulated, zero-suppressed PMT waveforms sampled every 4 ns (12,505 PMTs; one example = everything recorded from the first trigger to +50 µs). The chain is a sequence of small tree-based models (scikit-learn random forests and histogram gradient boosting), described in `baseline/obd_chain.py` and `baseline/run_baseline.py`:

1. **Pulse finding.** Pulse onsets above 0.25 PE (33 ADC counts). Each pulse is described by its own aligned samples, its first-ring neighbour PMTs in fixed angular slots, and a second-ring sum (`baseline/layoutb.py`).
2. **Stage 1, hit cleaner.** The probability that a pulse is real light rather than dark noise.
3. **Stage 2, flash classifier, per readout window.** Seven flash classes: positron, ⁶Li neutron capture, H neutron capture, positron + capture overlap, γ/β single, α single, proton recoil.
4. **Stage 3, position.** A per-pulse distance regressor, then forward-model triangulation per window. A calibration is applied to the reported positions only.
5. **Stage 4, pair classifier.** IBD vs ¹³C(α,n) vs accidental coincidence. It uses the Stage-2 probabilities, light, Δt, distances, and classical pulse-shape and time-of-flight features: Gatti filter (Gatti & De Martini 1962), tail-to-total, and TOF-corrected times.

**Output per example:** `[geo_score, prompt x, y, z, capture x, y, z]` in metres. `geo_score` is P(IBD) from Stage 4; candidates failing the physical preselection get P − 1. The reported capture point is the prompt-vertex fit, because the neutron-capture point of a geo-IBD lies within centimetres of the positron vertex.

## Files

| Path | What |
|---|---|
| `baseline/final_model.skops` | The trained v3r model (3,558,882 bytes; sha256 `db09b99a9f6e28d5fa3a71603a578838705065310bf95993fb7729247a0ecb92`) |
| `baseline/run_baseline.py` | `train` / `evaluate` / `export`; model loading with a type allow-list and a consistency guard |
| `baseline/obd_chain.py`, `layoutb.py`, `digitize.py`, `h5reader.py` | The chain, the pulse layout, the digitiser constants, and the HDF5 reader |
| `baseline/requirements.txt` | scikit-learn 1.9.1, skops 0.13.0 |
| `baseline/baseline_result.json` | Hyperparameters, seed, validation metrics and tolerances, wall time, and versions of the shipped model |
| `baseline/results/val_v3e_metrics.json`, `val_v3e_metrics_bootstrap.json` | Validation metrics and their bootstrap intervals |
| `baseline/results/test_v3e_eval.json` | The single test-split evaluation |
| `baseline/SHA256SUMS` | sha256 of every file in `baseline/` |

## Data

The dataset is on Zenodo: DOI **10.5281/zenodo.24322961** (reserved; the record is **not yet published**). It contains:
- train: 7 files, 260,497 examples;
- validation: 49,000 examples;
- test: 49,000 examples;
- per-file labels;
- `pmt_geometry.h5`.

Predictions must be made per example; example ids and file order carry no information.

The code expects one data folder holding:
- `train_NNN.h5` with `train_NNN.labels.h5` (labels are needed only for `train`);
- `val_NNN.h5`;
- `pmt_geometry.h5`.

## How to run

Environment used for the shipped results: Python 3.12.3, numpy 2.4.3, scipy 1.17.1, h5py 3.16.0, threadpoolctl 3.8.0, scikit-learn 1.9.1, skops 0.13.0.

```
pip install numpy==2.4.3 scipy==1.17.1 h5py==3.16.0 threadpoolctl -r baseline/requirements.txt
```

**Load the model in Python:**

```python
import sys; sys.path.insert(0, "baseline")
import run_baseline as rb
M = rb.load_model("baseline/final_model.skops")   # refuses unexpected types or inconsistent settings
```

**Per-example outputs without the task framework.** The `export` subcommand writes `<file>.chain.npz` per input file. It holds the example ids, `ml_score` (the geo score), the calibrated and raw ML positions, the Stage-4 features, and a conventional likelihood analysis:

```
python baseline/run_baseline.py export --data_dir DATA --model baseline/final_model.skops --output_dir OUT --files 'val_*.h5'
```

**Metrics (`evaluate`) and retraining (`train`).** These compute the declared task metrics through the SIDERIUS task package: `run_baseline.py` reads `../task/task.yaml` and the task's metric plugins. That package is part of the SIDERIUS task submission and is **not** in this repository.

```
python baseline/run_baseline.py evaluate --data_dir DATA --model baseline/final_model.skops --output_dir OUT
python baseline/run_baseline.py train    --data_dir DATA --seed 20261114 --output_dir OUT
```

`evaluate` writes `predictions.json` as `{"<file stem>:<6-digit index>": [geo_score, px, py, pz, cx, cy, cz]}` (metres), plus `metrics.json` and `metrics_bootstrap.json`. Seed 20261114 is the seed of the shipped model. The recorded run (`baseline_result.json`, 20 processes, Intel i9-12950HX) took:
- training: 686.7 s;
- evaluation: 323.5 s.

## Results

The score is `obd_combined` = 0.5 × selection + 0.5 × position:
- **selection** is the weighted geo-IBD efficiency at signal/background = 1;
- **position** is clip(1 − mean(median prompt error, median capture error) / 2 m).

| Split | obd_combined | 95 % interval | Selection (S/B = 1) | Median prompt error | Source |
|---|---|---|---|---|---|
| Validation | **0.702** (0.70229) | [0.677, 0.722] | 0.705 | 0.600 m | `baseline/results/val_v3e_metrics.json`, `val_v3e_metrics_bootstrap.json`, `baseline/baseline_result.json` |
| Test (scored once; see the task card for its partial overlap with an earlier development test file) | **0.690** (0.69049) | [0.670, 0.716] | 0.680 | 0.597 m | `baseline/results/test_v3e_eval.json` |

The validation interval comes from 200 bootstrap resamples, drawn within each class (`val_v3e_metrics_bootstrap.json`). These bootstrap files were computed on the original example order; rerunning them on the published files gives the same point values and intervals that differ only by resampling noise. The task card quotes intervals from an order-independent bootstrap (1,000 resamples). The test interval is the one recorded in `test_v3e_eval.json`.

## Known limitations

- In the simulation, α particles and the ⁶Li-capture triton share one scintillation time profile; the chain separates them by energy, Δt and position.
- About 15 % of IBDs fit in a single readout window. Their light is split between two pulses per PMT, which biases the distance estimates.
- The capture point is reported as the prompt fit (see above).
- The Stage-2 training labels of a small fraction of training accidentals whose second member is a ²¹⁴Bi–²¹⁴Po single have the β and α window classes swapped; the scored targets are unaffected.

## Credits

The overall chain is an original design. Classical methods used with credit: time-of-flight correction, tail-to-total, and the Gatti & De Martini linear filter (Nuclear Electronics II, IAEA, Vienna (1962), p. 265) as used in Borexino (Bellini et al., PRD 89, 112007 (2014), arXiv:1308.0443, §XII; Back et al., NIM A 584, 98 (2008)). Related ideas we credit:
- pair classification with decision trees on prompt/delayed features for KamLAND geoneutrinos: H. Song, "Machine Learning in KamLAND-Zen: An Old Detector Learning New ML Tricks", NPML 2023, KamLAND-Zen collaboration talk;
- per-hit noise classification: J. Li et al., PRD 114, 092006 (2026);
- binned time-profile pulse-shape discrimination: Rebber et al., JINST 16, P01016 (2021); Cheng et al., EPJC 84, 482 (2024);
- charge-based event features: Qian et al., NIM A 1010, 165527 (2021).

## Licence

See `LICENSE` in this repository.

## Contact

J. Seligman, University of Hawaiʻi at Mānoa, Department of Physics and Astronomy.
