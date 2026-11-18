# MOBY-DICK: Machine Optimization of Background Yield Discrimination, IBD Classification, and Kinematics 

=> Compact geoneutrino IBD selection and vertex baseline for a 17 kt Ocean Bottom Detector

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
| `run.py`, `requirements.lock`, `obd_runner/` | The standalone runner: setup, fetch, predict, evaluate, train, demo (see Quick start) |
| `demo/` | 200 validation examples, their labels and `pmt_geometry.h5` for `python3 run.py demo` (CC-BY-4.0) |
| `simulation/` | Everything needed to reproduce the detector simulation and the dataset build |

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

## Quick start: `run.py`

One script runs everything. It needs only Python 3.11–3.14 and internet access the first time. You do not need the SIDERIUS framework, a compiler, or admin rights.

```
python3 run.py demo                          # the model on the bundled 200-example sample; no data download
python3 run.py fetch                         # download + md5-check pmt_geometry.h5 and the validation files into ./data
python3 run.py predict --input FILE_OR_DIR   # predictions for any waveform files (labels not needed)
python3 run.py evaluate                      # the 9 task metrics on ./data/val_*.h5 (needs the labels files)
python3 run.py evaluate --predictions P.json # score your own predictions file, without running the model
python3 run.py train --yes                   # retrain from the train files (python3 run.py fetch --groups geometry,val,train)
```

- **Setup happens automatically on first use** (or run `python3 run.py setup`). It does three things:
  1. creates `./.venv` with Python's own `venv` module;
  2. downloads a sha256-checked `pip` wheel;
  3. installs `requirements.lock` with `pip --require-hashes --only-binary=:all: --no-deps`. These are the exact versions behind the shipped results: numpy 2.4.3, scipy 1.17.1, h5py 3.16.0, threadpoolctl 3.8.0, scikit-learn 1.9.1, skops 0.13.0, joblib 1.6.0 and their dependencies.

  Nothing is built from source, and nothing outside the lock is installed. Every later command re-runs itself inside `./.venv`. Tested on Linux x86_64, including a system Python 3.12 that has no `pip` or `ensurepip`. macOS is best effort; Windows is untested.
- **Outputs.**
  - `predict` and `demo` write `outputs/<command>/predictions.json` in the format `{"<file stem>:<6-digit index>": [geo_score, prompt x, y, z, capture x, y, z]}` (metres). A negative `geo_score` means the candidate failed the physical preselection. `--export` also writes `<file>.chain.npz`.
  - `evaluate` writes `metrics.json` (plus `predictions.json` and `metrics_bootstrap.json` when it runs the model).
- **Metrics without SIDERIUS.** `obd_runner/metrics.py` holds the task's metric arithmetic, copied verbatim from the task's metric plugin. On the saved v3r validation predictions it reproduces the SIDERIUS plugin's 9 metric values bit for bit. `run.py` swaps it in for the two SIDERIUS-dependent functions of `baseline/run_baseline.py`; `baseline/` itself is unchanged.
- **Demo sample** (`demo/`): the first 200 examples of the published validation file `val_000.h5`, which is stored in random order, plus their labels file and `pmt_geometry.h5`. Like the dataset, these files are licensed CC-BY-4.0 (DOI 10.5281/zenodo.24322961; see `demo/NOTICE.md`). The demo shows that the model runs. It claims no score: 200 examples cannot resolve the S/B = 1 selection.
- **Data download.** `fetch` downloads from the Zenodo record 10.5281/zenodo.24322961. It works only after the record has been published. Every file is checked against the size and md5 in `obd_runner/data_manifest.json`. Held-out test labels are never downloaded. If you already have the files, use `--source_dir DIR`.
- **Measured times** (Intel i9-12950HX, 24 processes; first run from a clean checkout):
  - `demo`, including the automatic setup: 20 s;
  - `predict` on the 200 examples alone: 6.5 s;
  - `evaluate` on the 49,000 validation examples: 316 s (the same predictions and metrics as the shipped run).

  The recorded full retrain took 686.7 s on 20 processes (`baseline_result.json`); its peak memory was not recorded.

## simulation/

`simulation/`: everything needed to re-simulate the OBD 17 kt detector (ratpac-two 4.4.0 geometry, detector tables, macros, generators, digitiser, dataset builder, seeds) and build your own training sets.
Start with `simulation/README.md` (container pin, geo-ν spectrum regeneration) and `simulation/REPRODUCE.md` (step-by-step recipe); seeds are in `simulation/SEEDS.md`.
The geoneutrino spectra (`IBD_GEO.ratdb`) are not redistributed; `simulation/tools/make_geo_ibd_spectrum.py` downloads and checksum-verifies them.

## How to run (without `run.py`)

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

**Metrics (`evaluate`) and retraining (`train`).** These compute the declared task metrics through the SIDERIUS task package: `run_baseline.py` reads `../task/task.yaml` and the task's metric plugins. That package is part of the SIDERIUS task submission and is **not** in this repository. Use `python3 run.py evaluate` / `train` to run them standalone (see above).

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
- pair classification with decision trees on prompt/delayed features for KamLAND geoneutrinos: H. Song, "Machine Learning in KamLAND-Zen: An Old Detector Learning New ML Tricks", NPML 2023, KamLAND-Zen collaboration talk (slides: "KamLAND-Zen's New ML Tricks");
- per-hit noise classification: J. Li et al., PRD 114, 092006 (2026);
- binned time-profile pulse-shape discrimination: Rebber et al., JINST 16, P01016 (2021); Cheng et al., EPJC 84, 482 (2024);
- charge-based event features: Qian et al., NIM A 1010, 165527 (2021).

## Collaboration

The Ocean Bottom Detector (OBD) project aims to deploy a kiloton-scale liquid-scintillator antineutrino detector directly on the ocean floor. Far from continental crust, it is to measure geoneutrinos from the Earth's mantle with directional (angular) sensitivity, for example above the Pacific Large Low Shear Velocity Province (Z. Xu et al., "Towards imaging Earth's large-scale structures by directional geoneutrino detection with Ocean Bottom Detector", arXiv:2606.13273 (2026), accepted for journal publication). The 17 kt detector simulated in this repository is an OBD design study, not a built detector.

Primary members of this project so far:
- Tohoku University (Japan)
- University of Hawaiʻi at Mānoa (USA)

The two groups work closely together: they meet every two weeks, co-author the OBD paper above, and have presented joint conference posters.

## Licence

See `LICENSE` in this repository.

## Contact

J. Seligman, University of Hawaiʻi at Mānoa, Department of Physics and Astronomy.
