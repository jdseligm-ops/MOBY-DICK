# Seeds

## Simulation seed formula

One Slurm array task = one chunk = one `rat` process with its own seed:

```
seed = BASE_SEED * 100000 + chunk_index          # jobs/sim_ibd_array.sbatch; rat -s <seed>
```

Every event stores `(seed, evid)`; per-event Geant4 RNG states are archived per chunk (`*.rndm_states.tar`), so
`/random/resetEngineFrom` can replay a single event. A requeued chunk restarts from scratch with the same seed and gives
identical events. Same-seed content hashes were identical on five CPU generations (Ivy Bridge, Haswell, Cascade Lake,
Ice Lake, Genoa; smoke seed 20261112, 10 events).

**Split by seed** (`dataset_build/tools/train_stage1.py: split_of`): outside the two φ wedges of the prompt vertex
(0–45° → `val_wedge`, 180–225° → `test_wedge`), `seed % 10` = 0–7 → `train`, 8 → `val_random`, 9 → `test_random`.

## BASE_SEED table

All production chunks: NEV = 200, `SHIELD=OBD_GLASS_SHIELD_GEL`, `LY=10000.0`, `LS_MATERIAL=obd_ls_li6_1p0`.
Machine-readable, with job ids and hashes: `provenance/production_runsets.json`.

| BASE_SEED | Run set (tag) | Chunks (indices) | `MACRO` | `SPEC` / `ISOTOPE` | `VOLUME` | In published data |
|---|---|---|---|---|---|---|
| 41 | geoU | 500 (0–499) | `ibd_geo` | `geo_U238` | — | yes |
| 42 | geoTh | 250 (0–249) | `ibd_geo` | `geo_Th232` | — | yes |
| 43 | reactor | 250 (0–249) | `ibd_geo` | `default` | — | yes |
| 51 | alphan | 250 (0–249) | `alphan_hepevt` | — | — | yes |
| 52 | po210_ls | 100 (0–99) | `singles_po210` | — | — | yes |
| 53 | k40_acrylic | 500 (0–499) | `singles_decay0` | `K40` | `^acrylic_vessel$` | yes |
| 54 | bi214_acrylic | 150 (0–149) | `singles_decay0` | `Bi214` | `^acrylic_vessel$` | yes |
| 55 | tl208_acrylic | 100 (0–99) | `singles_decay0` | `Tl208` | `^acrylic_vessel$` | yes |
| 56 | pa234m_ls | 25 (0–24) | `singles_decay0` | `Pa234m` | `^scintillator$` | yes |
| 57 | pb214_ls | 25 | `singles_decay0` | `Pb214` | `^scintillator$` | yes |
| 58 | bipo214_ls | 25 | `singles_decay0` | `BiPo214` | `^scintillator$` | yes |
| 59 | ac228_ls | 25 | `singles_decay0` | `Ac228` | `^scintillator$` | yes |
| 60 | pb212_ls | 25 | `singles_decay0` | `Pb212` | `^scintillator$` | yes |
| 61 | bipo212_ls | 25 | `singles_decay0` | `BiPo212` | `^scintillator$` | yes |
| 62 | tl208_ls | 25 | `singles_decay0` | `Tl208` | `^scintillator$` | yes |
| 63 | k40_ls | 25 | `singles_decay0` | `K40` | `^scintillator$` | yes |
| 71 | bi214_acrylic | 1,600 (indices ending in 8 or 9, 8–7999) | `singles_decay0` | `Bi214` | `^acrylic_vessel$` | **no** (option C, postponed) |
| 72 | po210_ls | 440 (8–2199, ending 8/9) | `singles_po210` | — | — | **no** |
| 73 | tl208_acrylic | 384 (8–1919, ending 8/9) | `singles_decay0` | `Tl208` | `^acrylic_vessel$` | **no** |
| 74 | pb214_ls | 16 (8–79, ending 8/9) | `singles_decay0` | `Pb214` | `^scintillator$` | **no** |
| 75 | ac228_ls | 4 (8, 9, 18, 19) | `singles_decay0` | `Ac228` | `^scintillator$` | **no** |
| 76 | bipo212_ls | 4 (8, 9, 18, 19) | `singles_decay0` | `BiPo212` | `^scintillator$` | **no** |
| 77 | pa234m_ls | 4 (8, 9, 18, 19) | `singles_decay0` | `Pa234m` | `^scintillator$` | **no** |

BASE_SEED 71–77: extra validation/test singles for a planned rebuild with unique accidental pairs ("option C"),
simulated 2026-11-17 with the identical code snapshot; chunk indices end only in 8 (val) or 9 (test), so none can enter
train. They are **not** in the published dataset v1.0.

Used earlier and never reuse: 1–2 (pilots), 11–13 and 21–33 (superseded air-shield / old-optics productions).
Smoke/reproducibility seed: 20261112. Local one-event demo seed: 20261114.

## Dataset-build seeds

| What | Seed / RNG key | Where |
|---|---|---|
| Digitiser master seed | `--digi-seed 1` | `build_dataset.py` |
| IBD / (α,n) example | `default_rng([digi_seed, 7, seed, evid])` (independent of the build layout) | `mode_events` |
| Accidental pairing | `default_rng([digi_seed, 13, task, split_code])` | `mode_accidentals` |
| Accidental digitisation | `default_rng([digi_seed, 17, split_code, task, index_in_shard, …])` | `mode_accidentals` |
| Val/test subsample | `--seed 20261114` | `subsample_group.py` |
| Val/test storage order | secret 256-bit key (`secrets.token_bytes`), **not published** | `shuffle_eval_group.py` |

Accidentals are therefore reproducible only with the same scan inputs, task count and budget:
train `NTASKS=40, BUDGET=120000, DT_MIX=0`; v3e val/test `NTASKS=60, BUDGET=100000, DT_MIX=0.6, DT_TAU=5300`
(`dataset_build/jobs/launch_v3_ds.sh`, `launch_v3e.sh`).
