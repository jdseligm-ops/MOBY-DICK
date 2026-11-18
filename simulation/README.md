# simulation/: everything needed to re-simulate the OBD 17 kt detector and build your own training sets

This folder holds the complete simulation and dataset-generation chain behind the published dataset
("OBD 17 kt simulated PMT waveforms for geoneutrino IBD selection and reconstruction", Zenodo, version 1.0: train `v3b`,
validation/test `v3e`). With it anyone can re-simulate any published event, simulate new events with the same detector,
and build new training sets in the same format.

- **Step-by-step recipe:** [`REPRODUCE.md`](REPRODUCE.md) ("reproduce a training set").
- **Seeds:** [`SEEDS.md`](SEEDS.md) (BASE_SEED table, seed formula, dataset-build RNG keys).
- **Which file equals which production file:** [`CODE_PROVENANCE.md`](CODE_PROVENANCE.md) (sha256 of every file).
- **Dataset description:** [`DATASET.md`](DATASET.md) (a copy of the dataset record's README; the Zenodo record is authoritative).

## Layout

| Path | What |
|---|---|
| `ratdb/OBD17kt/` | **Detector**: `OBD17kt.geo` (geometry: LS cylinder r 12 m × h 44 m, acrylic vessel, K-290 buffer, steel tank r 15 m × h 50 m), `PMTINFO_OBD17kt.ratdb` (12,505 × 20″ PMT positions/directions), `ENCAPSULATION_OBD.ratdb` (glass shields, gel-filled model `OBD_GLASS_SHIELD_GEL`), `MATERIALS_OBD.ratdb` (⁶Li-loaded LAB + PPO, buffer, …), `OPTICS_OBD.ratdb` and `PMT_OBD.ratdb` (ratpac-derived, GPL-3; see `NOTICE_RATPAC_DERIVED_GPL3.md`). `IBD_GEO.ratdb` is **not** included (see below). |
| `macros/` | ratpac macros: `ibd_geo.mac` (geo-U, geo-Th, reactor IBD), `alphan_hepevt.mac` (¹³C(α,n)¹⁶O), `singles_decay0.mac` (Decay0 radioactive singles), `singles_po210.mac` (²¹⁰Po α); `ibd_obd17kt.mac` and `ibd_smoke_validation.mac` (earlier/smoke versions). Placeholders `__X__` are filled by `jobs/run_chunk.sh`. |
| `tools/` | `make_geo_ibd_spectrum.py` (downloads Enomoto's spectra, checks pinned sha256, writes `IBD_GEO.ratdb`), `make_alphan_hepevt.py` ((α,n) HEPEvt generator), `extract_events.py` (ROOT ntuple → per-chunk `*.events.npz`, run inside the container), `make_obd_ratdb.py` (generates the ratdb tables from ratpac stock tables), `make_pmt_layout.py` (PMT layout), `timecmd.py`. |
| `jobs/` | `run_chunk.sh` (one chunk: frozen code snapshot → rat → extraction → `provenance.json` + `SHA256SUMS`), `run_chunk_local.sh` (**local single-chunk runner**, no Slurm), and Slurm **examples** `sim_ibd_array.sbatch` (production arrays), `repro_check.sbatch` (cross-CPU determinism check). |
| `env/pins.sh` | Container pins and the `ratx` wrapper (`apptainer exec`, never `apptainer run`). |
| `dataset_build/` | `tools/digitize.py` (digitiser v0.2; parameters and sources in `DIGITIZER.md`), `tools/build_dataset.py` (scan / events / accidentals / merge / geometry; the frozen v3e copy), `tools/build_dataset_v3b.py` (frozen v3b copy, built train), `rates.py` (yearly rates, activities), `subsample_group.py` (val/test subsample), `dataset_manifest.py` (md5 manifest + pair plans), `shuffle_eval_group.py` + `verify_shuffled_group.py` (val/test storage-order shuffle), `h5reader.py`, `train_stage1.py` (only `split_of` is used); `jobs/` Slurm **examples** and the launchers that built v3b and v3e. |
| `local_demo/` | One-event demo, event display and GUI on a workstation (`README.md` there). |
| `provenance/` | Production code manifests, `production_runsets.json` (every run set: BASE_SEED, chunks, settings, job ids, container, code hash), `plans_v3b.json` (accidental pair plans), the public val/test shuffle manifests. |
| `docs/` | `OBD17kt_DETECTOR_MODEL.md` (detector model; §3 and §6 are superseded, see its banner), `PHYSICS_AUDIT_20261113.md` (optics audit), `DETECTOR_SPEC_VERIFICATION.md` (every spec vs its source). Paths like `projects/OBD17kt_geo/...` in these docs refer to the authors' working tree; the files are in this folder. |
| `requirements-ml.txt` | Python pins of the host environment used for the dataset build (plus `h5py`). |

## Container (pinned; the image itself is not distributed)

ratpac-two 4.4.0 (Geant4 11.4.1, ROOT 6.36.12, Python 3.10.12, numpy 1.21.5 inside), official image, pinned by digest:

```bash
apptainer pull ratpac-two_4.4.0.sif docker://ratpac/ratpac-two@sha256:c85936d537dba4adba050c9fe4dde45a44e57454579ac96756007a925ff4c626
```

The SIF used in production has sha256 `3b6cc869a0b17db116a5e2d751b7f6ac534714a5f25e5f00810ff3d6c4d3ecba` (`env/pins.sh`;
`run_chunk.sh` aborts on a mismatch). A SIF you build yourself from the same digest may have a different file hash
(SIF build metadata); in that case put its own hash in `env/pins.sh` and record it. The physics content hash per chunk is
the real reproducibility check. Tested with apptainer 1.5.5.

## Geoneutrino spectra (`IBD_GEO.ratdb`): regenerate, never redistributed

`IBD_GEO.ratdb` is derived from S. Enomoto's ²³⁸U/²³²Th chain antineutrino spectra
(https://www.awa.tohoku.ac.jp/~sanshiro/research/geoneutrino/spectrum/), which carry no licence, so neither the spectra nor
the table are in this repository. Regenerate it:

```bash
python3 tools/make_geo_ibd_spectrum.py --check        # downloads both spectra, checks the pinned sha256, writes ratdb/OBD17kt/IBD_GEO.ratdb
sha256sum ratdb/OBD17kt/IBD_GEO.ratdb                  # production: 2b3a7e1366db7ed6a3cbb881109197a9af8198a475c91034346f579dad107c33
```

Pinned inputs: `AntineutrinoSpectrum_238U.knt` sha256 `e31894af4a8a89454da783d8a05c69f65d0683e9a5e63c2c9c1d4e89c3741f5a`,
`AntineutrinoSpectrum_232Th.knt` sha256 `e28088a857c42a09147b6e2561872dc222b1b42edbada8e6d9d2135ab20cd38a`.
A local copy can be supplied with `--cache DIR`.

**Fallback:** if the site moves or the files change, the hash check fails on purpose and nothing is written. Then obtain
the original files from the author of the spectra (S. Enomoto) and pass them with `--cache`; only the pinned bytes
reproduce the published geo-ν events. Reactor IBD (`SPEC=default`, stock ratpac table), (α,n) and all singles do not need
this table.

## Licences and credit

- Code and tables in this repository: GPL-3.0 (repository `LICENSE`). `OPTICS_OBD.ratdb` and `PMT_OBD.ratdb` are derived
  from ratpac-two stock tables (GPL-3.0); see `ratdb/OBD17kt/NOTICE_RATPAC_DERIVED_GPL3.md`.
- Please cite ratpac-two, Geant4, and S. Enomoto's geoneutrino spectra (S. Enomoto, PhD thesis, Tohoku 2005;
  S. Enomoto et al., EPSL 258, 147 (2007)) when using the geo-ν samples.
- The published data are CC-BY-4.0 (see the Zenodo record).

## Known simulation limitations (do not silently "fix"; they define what the data are)

Stock SNO+ LAB/PPO optics (not measured OBD scintillator); the ⁶Li-capture triton uses the α-like pulse table (so ⁶Li
captures and ²¹⁰Po share one pulse shape); the PMT type (KamLAND 20″ vs high-QE), gel-filled shields, TTS read as FWHM
and the generated PMT layout are assumptions; light yield not reduced for ⁶Li loading; simulated photocathode coverage
≈ 39 % (35.4 % on paper); a spurious ~20 MeV γ in ~1.5 × 10⁻⁴ of ⁶Li captures (Geant4 NeutronHP; kept);
`SCINT_RISE_TIMEneutron` in `OPTICS_OBD.ratdb` is not read by ratpac (no effect). Not simulated as sources: ²¹⁰Bi,
¹⁴C, ⁸⁵Kr, Rn, PMT/shield/steel/buffer/seawater radioactivity, cosmogenics, atmospheric ν, afterpulses and flashers.
Details: `DATASET.md` §9 and `docs/`.
