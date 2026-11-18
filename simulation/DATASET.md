# OBD 17 kt simulated PMT waveforms for geoneutrino IBD selection and reconstruction (dataset v1.0: train v3b, val/test v3e)

> **Copy of the dataset record's README** (draft text of 2026-11-17, synchronised by hand). The Zenodo record is authoritative; if the two differ, the record wins. Contact details are in the record, not here.

## 1. What this is

This is simulated raw detector data from a proposed 17 kt **Ocean Bottom Detector (OBD)**: a ⁶Li-loaded liquid-scintillator antineutrino detector. It is an OBD-like design study, not a built detector.

- **Model inputs:** every example is the zero-suppressed, 4 ns-sampled waveform of each of 12,505 20-inch PMTs. It covers everything the detector records from its first trigger up to +50 µs.
- **Truth:** a separate, row-aligned labels file carries the truth for the following chain:

```
raw 4 ns PMT waveforms
  -> (1) pulse/hit: real light or noise (dark noise, electronics)
  -> (2) flash class per readout window (positron, 6Li capture, H capture, prompt+capture overlap,
         radioactive decay, alpha, proton recoil)
  -> (3) neutron-capture identification (capture nucleus, time, point)
  -> (4) event class: geoneutrino IBD vs 13C(alpha,n) vs accidental coincidence (reactor IBD as a check)
  -> positions: prompt vertex and neutron-capture point
```

It was produced for the SIDERIUS hackathon Track 1 task "OBD 17 kt geoneutrino IBD" (https://siderius.scitra.org/; the task card ships with the task package).

- **Code:** the baseline model, its weights and the code that loads and runs it are in this repository; the simulation and dataset-generation code (geometry, detector tables, generators, digitiser, dataset builder, seeds) is in its `simulation/` folder.
- **Licence:** CC-BY-4.0 (data). The code repository is GPL-3.0.

## 2. Files and pairing

The record holds 19 HDF5 files (23.77 GB in total) plus this `README.md` and `PROVENANCE.json`.

- `X.h5` holds the **inputs only** (waveforms).
- `X.labels.h5` holds the **truth** for the same examples, **in the same row order**.
- The join key is the example index *e* (0-based) within the file pair. The example id used in prediction files is `"<file stem>:<6-digit e>"`, for example `val_000:000123`.

| File | Bytes | md5 | sha256 |
|---|---|---|---|
| `pmt_geometry.h5` | 308312 | `19e3216ca53ea47ca20b1824fe0415c3` | `adcfdb5fb235014b844064e03cf97346b91e58d10d37372ba544b7becfca2c20` |
| `train_000.h5` | 2509506080 | `346a699e36d1bb0501ca390c48f8c8ec` | `4147fb9f291cab904b49bc9c2ccebb55609e38c8307642b32235a5b5a10f66a5` |
| `train_000.labels.h5` | 300398224 | `18ebf5d3249e0394524cb046543ccb07` | `d0b78db9f1fd7b4dd7fbff875aefcaef5f095a2b8744c5cb21cbe249e04ffb96` |
| `train_001.h5` | 2506917960 | `5e3b47b2a42ad640b1de579810ae8446` | `7285ffa002fc2e5802064d4d1f76033279ef34da4f9210a67ecc1697ec6cf1f5` |
| `train_001.labels.h5` | 300377978 | `8434e061bd97e91ce3913d5f276b7533` | `9d4a1bafde9fa53f6bf615b87eae20ed1f443abf1e2458061057dd9914a815d9` |
| `train_002.h5` | 2421197087 | `b501b6760613ce851a06db239d4b6add` | `50a3546d4aff6b9b935762dd0570e2ad95bfcad7503a6219f74f247442064358` |
| `train_002.labels.h5` | 288645386 | `bc7e1cf40cad277aa165a2b6747c6b0b` | `cee194aad75f9a6966aac9173d5bd7d30327887e6056e5141c88fa99c60b12b6` |
| `train_003.h5` | 2426926877 | `0b1852338f455eae8d7763e2c16925b3` | `11ce8e573c13210f8659b9c32d0e01439801e1e223564ec0d11fd118fac0b02f` |
| `train_003.labels.h5` | 248673598 | `365dfa6ee27b008da145701b83b80a02` | `ae30c39c04fb1d3970f83edd3a84fe88fcf21612d90b98161fa0f83f4e9d1c71` |
| `train_004.h5` | 2431922163 | `a904df565760fd1959020f3417933c78` | `710b18d4f8b42435294f17b544033541dfd66539e2205cf1396099c8f514d8b5` |
| `train_004.labels.h5` | 240871366 | `82d75670d39053e619766115d55ab2ab` | `01835077b7c8e1e33776e62302455cccee7cbdc9899eb7ea7fafd6365f2d4b6f` |
| `train_005.h5` | 2420106705 | `235b1345a56a0d3de5898b328d18f70a` | `47b48368cbb1f83397a754d0e9b6b5b51d809200ae651a4ad8ca94a5a8530ed3` |
| `train_005.labels.h5` | 292238133 | `97587e1fa3c754ad0ff01122ec709112` | `114999556dfcce3ca426426d6e0b435ee58f981b5f9cf43bc7690c9300e27d87` |
| `train_006.h5` | 808645830 | `c9368609cb6d0f4ab392bab22cdf5e3f` | `daf57cc37f8d027724c6ccd0618041b43d2410ff405d39adb30fbc44d94dcbfe` |
| `train_006.labels.h5` | 111228063 | `58fdb7e1fae7e827cac0eb4cf169bd2b` | `c73eceeb177d69185dadcb276f33f0e89f5f2cdd12866d2a5da0e4e69bc85f78` |
| `val_000.h5` | 2879772420 | `b4087fd65a8e38a5b1360fff1377c40c` | `6cda39443ef95051f3a30c7f84c09c09be359417f53f5148ade8fc00ad43275d` |
| `val_000.labels.h5` | 346773005 | `cad0513b6c09d6198b62ef19c58d34b6` | `eea9c61170235bca1e79a9527a81e4ad3af0081595839fd904dbbf3dcc393b77` |
| `test_000.h5` | 2883688808 | `1ac88d37d2889ac7be765da87843658c` | `6853feb2c7b0736de7f9325008c6cdb7a3e435a1f47df4db282327e7242f570d` |
| `test_000.labels.h5` | 346843121 | `b34e1556ac1786b40a2fa7e4199bbf2b` | `24744418146af8a834fe00d419abfc425b710cbf96bb5d8bfcb10c295e4d801c` |

The waveform files carry two file-level attributes:
- `detector_json`: the detector configuration;
- `format`: it reads "see docs/DATASET.md", and *this README is that document*.

The labels files carry no attributes: this README is their schema.

## 3. Splits and counts

**Split rule** (by the prompt vertex azimuth φ and the source simulation chunk seed):

| Condition | Split |
|---|---|
| φ ∈ [0°, 45°) | `val_wedge` |
| φ ∈ [180°, 225°) | `test_wedge` |
| otherwise, seed % 10 = 0–7 | `train` |
| otherwise, seed % 10 = 8 | `val_random` |
| otherwise, seed % 10 = 9 | `test_random` |

- Accidental singles are assigned to a split by their own seed and vertex *before* pairing. No simulated decay appears in two splits.
- The wedges test for memorisation of detector position.

| Group | Examples | geo-U | geo-Th | reactor | (α,n) | accidental |
|---|---|---|---|---|---|---|
| train (train_000–006) | 260,497 | 58,845 | 28,140 | 29,882 | 25,353 | 118,277 |
| val_000 (val_random + val_wedge, 24,500 each) | 49,000 | 6,000 | 2,000 | 2,000 | 3,000 | 36,000 |
| test_000 (test_random + test_wedge, 24,500 each) | 49,000 | 6,000 | 2,000 | 2,000 | 3,000 | 36,000 |

- **Train** is every train-split example of the production.
- **Val and test** are seeded subsamples (seed 20261114) of a larger build, reweighted per (sub-split, class, true-separation bin) by available/kept. Accidentals are allocated over the true A–B separation bins 0–1.5 / 1.5–3 / 3–4.5 / 4.5–6 / 6–9 / 9–12 / 12–20 / > 20 m as 300 / 300 / 300 / 300 / 1,200 / 1,800 / 5,200 / 8,600 per sub-split.
- **Test labels** are public as a final held-out check. Do not use them for model selection.
- **Storage order:** validation and test examples are stored in a random order drawn from a secret key (not published), so the example index and storage order carry no class information. The waveform files carry only `detector_json` and `format`. An earlier, unpublished version of these two files was stored class-sorted; a pre-publication audit found that the index then revealed the class, and both files were rewritten in the random order with every example byte-identical (verified for all 49,000 examples of each file). The training files are stored grouped by class (`train_000`/`train_001` hold only accidentals); train labels are public, so this is not an evaluation leak, but shuffle when training. **Never use the example index or storage order as information.**

## 4. Waveform file `<group>_NNN.h5` (model input)

All times are on one **global 4 ns sampling clock per example**. Sample 0 is the start of the example's first readout window. No Monte Carlo time origin survives, and one random sub-sample clock phase is applied per example.

| Dataset | dtype | Shape | Meaning |
|---|---|---|---|
| `examples/win_off` | int64 | (n+1) | example *e* owns windows `win_off[e]:win_off[e+1]` |
| `examples/seg_off` | int64 | (n+1) | example *e* owns segments `seg_off[e]:seg_off[e+1]` |
| `windows/start_sample` | int64 | (n_win) | window start in samples since the example's first window start; 0 for the first window, ≤ 12,500 (50 µs). The difference between two windows is the time between triggers, exact to 4 ns. |
| `windows/trigger_sample` | int16 | (n_win) | trigger position inside the window: **always 50** (200 ns pre-trigger, 1,000 ns post-trigger; windows are 300 samples = 1.2 µs) |
| `segments/pmt` | uint16 | (n_seg) | PMT id = index into the `pmt_geometry.h5` arrays (0…12,504) |
| `segments/window_in_example` | uint8 | (n_seg) | window index within the example (0, 1, 2) |
| `segments/start_sample` | int16 | (n_seg) | first stored sample of the segment, relative to its window start (0…299) |
| `segments/length` | uint16 | (n_seg) | number of samples in the segment |
| `segments/sample_off` | int64 | (n_seg+1) | segment *s* owns `samples[sample_off[s]:sample_off[s+1]]` (file-global offsets) |
| `samples` | int16 (gzip) | (n_samples) | ADC counts above baseline, pulses positive. 1 mean single photoelectron ≈ 130 ADC at its peak. Baseline noise σ = 6.5 ADC, so values can be negative. 14-bit range, never saturated in this set. |

**Notes:**
- **Windows can overlap.** After a trigger the detector is dead until the window ends, so the next window can start 250 samples later. Its 200 ns pre-trigger then overlaps the previous window's last 200 ns. This happens in about 5 % of second windows, mostly prompt/capture pairs less than 1.2 µs apart.
- **Zero suppression:** a sample is kept if it is above 33 ADC (0.25 PE), plus 2 samples before and 4 after; contiguous kept samples form one segment.
  - Electronic-noise-only segments are also simulated on PMTs that had no photoelectron in a window: Gaussian-tail crossings, 7 samples long.
  - These are appended **after** the PMT-sorted segments of each window (Z2 L5). About 31 % of them peak at exactly 33 ADC because of rounding (Z2 L6).
  - Do not use segment order as information.
- **Dark noise:** 40 kHz per PMT, generated within ±2 µs of each light cluster. That covers every recorded window.
- **Digitiser model** (`digitize.py` v0.2):
  - lognormal R3600-like single-PE pulse peaking 20 ns after the photoelectron;
  - gain spread σ/μ = 0.50 per photoelectron;
  - trigger: ≥ 120 photoelectrons in 100 ns.
  - Not modelled: afterpulses, prepulses, overshoot, gain spread between channels, dead channels, crosstalk.
- **Candidate condition** (applied identically to every example): ≥ 246 PMTs with a pulse onset in −20…+80 ns of window 0's trigger. An onset is an up-crossing of 33 ADC. Anyone can compute it from the waveforms.

## 5. Labels file `<group>_NNN.labels.h5` (truth; never a model input)

### 5.1 `truth/*`, one row per example (length n)

| Field | dtype | Units / codes | Meaning |
|---|---|---|---|
| `cls` | int64 | 0 geo-U IBD, 1 geo-Th IBD, 2 reactor IBD, 3 ¹³C(α,n)¹⁶O, 4 accidental | event class |
| `weight_per_year` | float64 | events / yr | how many events per year this example represents **within its sub-split**. Each sub-split = 1 yr, so a val/test file (2 sub-splits) sums to 2 yr. Use this for every rate, efficiency or S/B. |
| `split` | bytes | `train`, `val_random`, `val_wedge`, `test_random`, `test_wedge` | sub-split |
| `prompt_x`, `prompt_y`, `prompt_z` | float64 | mm, detector frame (§6) | IBD: interaction vertex (positron start). (α,n): reaction vertex. Accidental: vertex of single A. |
| `delayed_x`, `delayed_y`, `delayed_z` | float64 | mm | IBD/(α,n): neutron capture point (start of the capture products α+t or d; otherwise the last neutron track point). Accidental: vertex of single B. |
| `dt_true_ns` | float64 | ns | IBD/(α,n): true capture time minus vertex time. It can exceed 50 µs (0.05 % of IBD, 0.13 % of IBD + (α,n) in the validation file), in which case the capture is not in the example. Accidental: time offset of B relative to A, in [0, 50 µs). |
| `n_target` | int64 | 1 ⁶Li (α+t seen), 2 H (deuteron), 3 other/unknown, −1 not applicable (accidental) | capture nucleus |
| `overlap` | int64 | 1 if `dt_true_ns` < 1,000, else 0; −1 for accidentals | prompt and capture light mix within one window |
| `ep_ke` | float64 | MeV | IBD: positron kinetic energy. (α,n): positron kinetic energy of the ¹⁶O(0⁺, 6.049 MeV) e⁺e⁻ pair branch when present (present in about 7 % of generated and 8 % of published (α,n) examples), else NaN. NaN for accidentals. |
| `n_ke` | float64 | MeV | primary neutron kinetic energy (NaN for accidentals) |
| `edep_a` | float64 | MeV | energy deposited in the scintillator (Birks-unquenched) by the **whole simulated event**. For IBD/(α,n) it **includes the capture** (median `edep_a` − (`ep_ke` + 1.022 + 4.78) = 0.00 MeV for ⁶Li captures), so it is **not the prompt energy** (12.30 MeV for fully contained (α,n) events). Accidental: single A. |
| `edep_b` | float64 | MeV | accidental single B (NaN otherwise) |
| `prompt_nhit` | int64 | PMTs | the candidate-condition statistic (§4); ≥ 246 everywhere |
| `triggered` | bool | | always True in the published files |
| `sample_a`, `sample_b` | bytes | geoU, geoTh, reactor, alphan; singles: `po210_ls`, `bi214_acrylic`, `tl208_acrylic`, `k40_acrylic`, `pa234m_ls`, `pb214_ls`, `bipo214_ls`, `ac228_ls`, `pb212_ls`, `bipo212_ls`, `tl208_ls`, `k40_ls` | source sample of the event / single A, and of single B (empty if not applicable) |
| `seed_a`, `evid_a`, `seed_b`, `evid_b` | int64 | −1 if not applicable | source simulation ids (§7) |
| `pair_i`, `pair_j` | bytes | | accidentals: the component pair (equals `sample_a`/`sample_b`) |
| `q_close` | int64 | 0/1, −1 | accidentals: A–B separation < 3 m |
| `importance` | float64 | | accidentals: pair-sampling × separation post-stratification × Δt importance factor (pre-subsample) |
| `N_ij`, `M_ij` | float64 (int64 in train_000/001) | /yr; count | accidentals: true yearly rate of pair (i,j) in the split; number of pairs of (i,j) drawn in the full build |

- In train, `weight_per_year = N_ij · importance / M_ij` for accidentals.
- In val/test, the subsample factor is also folded in, so use `weight_per_year`.
- Fill values: −1 (integers), NaN (floats), empty string.
- String fields are fixed-width bytes whose width differs between files. `real_pe/win` is uint8 in train and int16 in val/test.

### 5.2 `real_pe/*`: real photoelectrons (hit-level truth)

| Field | dtype | Meaning |
|---|---|---|
| `off` | int64 (n+1) | example *e* owns photoelectrons `off[e]:off[e+1]` |
| `pmt` | uint16 | PMT id |
| `t` | float32 | ns since the example's first window start, in the same frame as the waveforms. It includes the PMT transit-time spread (σ 3.27 ns) and the per-example clock phase. The pulse peaks about 20 ns later. |
| `win` | uint8/int16 | the window whose time span contains `t`. In overlapping windows it is the **later** window, so match by time, not by `win`. |
| `label` | int8 | IBD/(α,n): **1** = photon created before the true neutron-capture time, **2** = created at or after it. Accidentals: **1** = single A, **2** = single B. |

- **Only real (physics) photoelectrons inside a readout window are listed.** Everything else in the waveforms is dark noise or electronic noise.
- Photoelectrons outside every window are omitted, including those in the 64 ns before a window start whose pulse tail leaks into it.
- Per-photoelectron gains and dark-noise photoelectrons are **not** published.
- **Caveat on `label`:** for IBD/(α,n) it is a **time split, not a particle-ancestry label**.
  - In fast captures (17 % within 1 µs), late scintillation light of the positron counts as 2.
  - In ~0.3 % of events the neutron is captured in flight within nanoseconds, so almost all light counts as 2.
  - For dt ≫ 1 µs, label 1 = prompt flash and label 2 = capture flash.
  - For accidentals the label is exact by source. A BiPo single's β and α share one label.

## 6. `pmt_geometry.h5`

`x, y, z` (mm) and `u, v, w` (unit vector the PMT faces, inward) are float32 arrays of length 12,505. Attributes: `n_pmt` and `units`.

**Detector frame:** origin at the detector centre, z along the cylinder axis.

| Element | Extent |
|---|---|
| Scintillator target | r ≤ 12.0 m, \|z\| ≤ 22.0 m |
| Acrylic vessel | to 12.05 / 22.05 m |
| PMT centres | r = 14.63 m (wall: 79 rings × 125); \|z\| = 24.63 m (1,315 per cap) |

Predictions in the task are in **metres**; truth is in **mm**.

## 7. How the data were made (provenance)

**Simulation:**
- ratpac-two 4.4.0 (Geant4 11.4.1, `Shielding` + NeutronHP), container `docker://ratpac/ratpac-two:4.4.0` at digest `sha256:c85936d537dba4adba050c9fe4dde45a44e57454579ac96756007a925ff4c626`;
- full optical-photon transport.

**Detector** (`detector_json`):
- OBD 17 kt v1 geometry; steel tank r 15 m, h 50 m; buffer oil; acrylic vessel;
- LAB + PPO 3 g/L + 1.0 wt % ⁶Li, 10,000 photons/MeV;
- stock SNO+ LAB/PPO optics (re-emission only below 340 nm; PPO absorption scaling 1.2; OPTICS table sha256 `84128bc2…`);
- 12,505 R3600-type 20″ PMTs, QE 23 % at 390 nm, in gel-filled borosilicate shields.

**Pulse shapes:** SNO+ (JINST 16 P05009) e⁻ and α tables.

**Measured from these files:**

| Quantity | Value |
|---|---|
| Prompt light | ≈ 400 PE/MeV (≈ 340 central; 395–415 by estimator) |
| ⁶Li capture | median ≈ 270 PE (≈ 230 central): a median of about 270 photoelectrons for a ⁶Li capture (about 230 in the central volume, r < 8 m and \|z\| < 18 m; about 300 nearer the PMTs) |
| H capture (2.22 MeV γ) | median ≈ 955 photoelectrons |
| Capture time | τ = 5.3 µs |
| Captures on ⁶Li | 97.4 % |
| Neutron drift | median 3.9 cm |

**Generators:**

| Class | Generator |
|---|---|
| geo-ν | ratpac IBD generator with S. Enomoto's ²³⁸U/²³²Th chain spectra (downloaded and checksum-pinned, not redistributed) |
| reactor | ratpac default spectrum (not site-specific) |
| ¹³C(α,n)¹⁶O | own HEPEvt generator: ground state 91.5 %, excited states 8.5 % (Zhao et al. 2014, Table 1), split 6.9 % 6.049 MeV e⁺e⁻ / 1.6 % 6.130 MeV γ (a proxy from KamLAND's detected counts); the α's pre-reaction energy loss is simulated as an α track; neutron energies up to 7.3 MeV (KamLAND 2008) |
| radioactive singles | Decay0 (acrylic ²¹⁴Bi, ²⁰⁸Tl, ⁴⁰K; LS U/Th/K chain members) and ²¹⁰Po α (70 Bq) |

**Yearly rates** (summed `weight_per_year` per sub-split; before the candidate condition in brackets):

| Class | Rate /yr |
|---|---|
| geo-U | 97.7 (100.09; OBD 17 kt prediction, Ohno 2024 Table 5.6 = arXiv:2606.20780 Table III (rounded to 100 there), which already folds in that study's detection efficiency and livetime) |
| geo-Th | 23.4 (24.98; same source, which already folds in that study's detection efficiency and livetime) |
| reactor | 67.7 (67.84; same source, which already folds in that study's detection efficiency and livetime) |
| (α,n) | 107.3 (127 = 70 Bq ²¹⁰Po × 5.75 × 10⁻⁸ n/α, Zhao et al. 2014 Table 1) |
| accidentals | 1.54–1.59 × 10⁶ |

**Accidentals:**
- Two independently simulated singles are overlaid at the photoelectron level and then digitised together.
- N_ij = (A_i f_prompt,i)(A_j f_trig,j) × 50 µs × 1 yr. The largest pairs are acrylic ²¹⁴Bi → LS ²¹⁰Po (1.02 × 10⁶ /yr), ²¹⁴Bi → ²¹⁴Bi (2.4 × 10⁵) and ²⁰⁸Tl → ²¹⁰Po (1.9 × 10⁵).
- Pairs are importance-sampled in true separation (35 % < 3 m, 35 % 3–6 m, 30 % uniform) and post-stratified.
- Δt is uniform in train. In val/test it is drawn from 0.6·Exp(5.3 µs) + 0.4·U(0, 50 µs) with weight u/q. The weighted Δt shares come out at the uniform values (0.10 / 0.10 / 0.20 / 0.60 for 0–5 / 5–10 / 10–20 / 20–50 µs).
- ²¹⁰Po alone reaches the candidate condition only at the edge of its light distribution. In the singles scan about 1 × 10⁻⁴ of decays pass, but most of these pairs fail again after overlay and digitisation. The published files therefore hold few ²¹⁰Po-first pairs (train 97 examples, 45/yr; validation 5 examples, 2.9/yr over two sub-splits; test none), and they are included with their weights. This rare ²¹⁰Po prompt leakage (f ≈ 10⁻⁴) is represented by a single simulated decay per split, reused across pairs: all 97 train ²¹⁰Po-first pairs share one ²¹⁰Po decay, and the 5 validation pairs share one `val_wedge` decay.

**Seeds:**
- Every event has simulation seed `seed = BASE_SEED × 100000 + chunk` and ratpac event id `evid`. `evid` is ratpac's event index and can exceed the 200 generated events per chunk.
- BASE_SEED per sample:

  | BASE_SEED | Sample |
  |---|---|
  | 41 | geoU |
  | 42 | geoTh |
  | 43 | reactor |
  | 51 | alphan |
  | 52 | po210_ls |
  | 53 | k40_acrylic |
  | 54 | bi214_acrylic |
  | 55 | tl208_acrylic |
  | 56 | pa234m_ls |
  | 57 | pb214_ls |
  | 58 | bipo214_ls |
  | 59 | ac228_ls |
  | 60 | pb212_ls |
  | 61 | bipo212_ls |
  | 62 | tl208_ls |
  | 63 | k40_ls |

- (sample, seed, evid), together with the container, macros and ratdb tables (in `simulation/` of this repository), re-simulates an event.
- Digitiser seed: `digi_seed` = 1. IBD/(α,n) examples use RNG key [1, 7, seed, evid]. Accidentals use a key that includes build-shard indices that are not published, so their waveforms are reproducible only by re-running the build.
- Val/test subsample seed: 20261114.
- Code: this repository (baseline in `baseline/`; simulation and dataset generation in `simulation/`, seeds in `simulation/SEEDS.md`).
- Provenance: `PROVENANCE.json` in this record (container digest, versions, seeds, subsample rule, file hashes, and the sha256 of the secret val/test permutation).

## 8. How to derive each target from the published fields

The reference implementation is the shipped baseline (code repository: `baseline/h5reader.py`, `layoutb.py`, `obd_chain.py`).

| Target | Recipe |
|---|---|
| (1) **hit real vs noise** | For each PMT and window, sum the single-PE pulse template (`digitize.pulse_shape`, unit gain × 130 ADC) of the `real_pe` with that PMT and `t` in [window start − 64 ns, window end). Call a pulse onset (an up-crossing of 33 ADC) *real* if this real-light waveform is ≥ 16.5 ADC at the onset sample or the next one; otherwise it is noise (`layoutb.compile_rows`). Its source is 2 if label-2 light gives > ½ of the real amplitude. Limitation: the truth uses unit gain, and dark-photoelectron contributions to mixed pulses are unknown. |
| (2) **flash class per window** | Count label-1 (p) and label-2 (d) photoelectrons whose `t` lies in the window (match by time). IBD: d/(p+d) < 0.1 → positron; p/(p+d) < 0.1 → ⁶Li or H capture by `n_target`; else overlap. (α,n): window 0, or p/(p+d) ≥ 0.1 → proton recoil (plus ¹⁶O* γ/e⁺e⁻ and ¹²C 4.4 MeV γ, not separated); else capture. Accidentals: the dominant label picks `sample_a` or `sample_b`; ²¹⁰Po → α; BiPo → the second time-cluster of the same single is the α; others → radioactive decay. (`obd_chain.window_class`; note that its BiPo rule uses the example window index, which mislabels BiPo as member B; see §9.) |
| (3) **neutron capture** | `n_target`, `dt_true_ns`, `delayed_x/y/z`. The capture window is the one holding the label-2 light. |
| (4) **event class** | `cls`, weighted by `weight_per_year`. The task metric excludes reactor (cls 2) from both signal and background. |
| **positions** | `prompt_x/y/z` and `delayed_x/y/z` (mm). For accidentals they are the A and B decay vertices. |

## 9. Known limitations, caveats and shortcuts (read before use)

**Simulation:**
- The ⁶Li-capture triton uses the α-like pulse table, so ⁶Li captures and ²¹⁰Po have the same pulse shape.
- PMT model (KamLAND 20″ vs high-QE), gel-filled shields, TTS read as FWHM, and the generated PMT layout are assumptions. The 7.7 ns TTS is read as FWHM, consistent with the 7.3 ns FWHM measured for the R3600 (Okajima et al. 2016, Table 3).
- ²¹⁰Po light: the simulated 5.3 MeV ²¹⁰Po α gives about 0.54 MeV electron-equivalent (median about 210 photoelectrons, against about 270 for a ⁶Li capture). KamLAND sees ²¹⁰Po at about 0.3 MeV (PRC 92, 055808), and SNO+ tunes the α Birks constant to 80.3 µm/MeV (EPJC 85, 17; erratum EPJC 85, 296), above the 71 µm/MeV used here, so the simulated ²¹⁰Po light is probably too high. If the real ²¹⁰Po is dimmer, ²¹⁰Po and ⁶Li captures are easier to separate by energy than in these files (accepted as an assumption).
- The light yield is not reduced for ⁶Li loading.
- Simulated photocathode coverage is ≈ 39 % (35.4 % on paper).
- About 1.5 × 10⁻⁴ of ⁶Li captures (23 of 163,830 in these files; none in test) carry a spurious ~20 MeV γ (Geant4 NeutronHP final-state error). It is kept; such capture windows hold 7,000–12,200 photoelectrons.

**Backgrounds not simulated as sources:**
- ²¹⁰Bi (the largest gap), ¹⁴C, ⁸⁵Kr, Rn. ²¹⁰Bi (not simulated) is likely the largest missing background: if the 70 Bq of ²¹⁰Po is fed by ²¹⁰Pb (radon ingress), ²¹⁰Bi β decays (end point 1.16 MeV) occur at the same rate. An order-of-magnitude estimate (assumption, not simulated) gives 2 × 10⁵–1 × 10⁶ ²¹⁰Bi → ²¹⁰Po pairs per year within 50 µs, uniform in the scintillator volume; in KamLAND ²¹⁰Bi was the leading background below 1 MeV (PRC 92, 055808).
- radioactivity of the PMT glass, shields, steel, buffer and seawater ⁴⁰K;
- cosmogenics (⁹Li/⁸He, fast neutrons), atmospheric ν;
- PMT afterpulses and flashers.

**Labels:**
- `real_pe/label` is a time split for IBD/(α,n) (§5.2).
- `edep_a` is the whole-event energy.
- About 0.2 % of IBD/(α,n) examples lack either the capture flash (capture after 50 µs or not triggered) or the prompt flash (the example starts at the capture). Their truth positions are still filled.
- geo-U has a small tail above the ²¹⁴Bi end point (3.27 MeV): 0.044 % of geo-U examples, matching the 0.049 % that the input spectrum predicts. It comes from the ²¹⁰Tl branch of the ²³⁸U chain (Q = 5.48 MeV, via the 0.02 % α branch of ²¹⁴Bi), included in Enomoto's chain spectrum, which extends to 4.39 MeV. This is real physics, not a bug.

**Shortcuts (do not exploit):**
- **Storage order** (§3): random for val/test, class-grouped for train. Do not use the example index or order.
- **Reused singles (L4).** Accidental pairs reuse simulated single decays: in val about 5,400 distinct prompt singles serve 36,000 pairs (≈ 6.7 uses each). Only dark noise, gains and clock phase differ, so near-duplicate light patterns mark accidentals. IBD and (α,n) events are all unique. The reuse comes from the size of the simulated singles pool, not from a sampling choice: for the samples that dominate the rate, the published files already use essentially every eligible single of their split. The rare ²¹⁰Po-first pairs are an extreme case: one ²¹⁰Po decay per split (all 97 in train, all 5 in validation). **Predict each example on its own; never compare examples** (within a batch, across batches through model state, or across files). Validation/test accidentals rebuilt from unique single decays: planned as a new dataset version.
- Segment order marks electronic-noise-only segments (§4).

## 10. Citation

> J. Seligman, "OBD 17 kt simulated PMT waveforms for geoneutrino IBD selection and reconstruction", Zenodo, version 1.0, doi:10.5281/zenodo.24322961 (2026).


Please also cite ratpac-two and Geant4, and S. Enomoto's geoneutrino spectra (https://www.awa.tohoku.ac.jp/~sanshiro/research/geoneutrino/spectrum/).
