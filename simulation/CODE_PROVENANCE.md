# Code provenance: which file here equals which file that made the published data

The published dataset (Zenodo record, version 1.0: train `v3b`, validation/test `v3e`, shuffled) was made by code that was
frozen into a snapshot at the start of every run set, with a `CODE_MANIFEST.sha256` per snapshot. Those manifests are in
`provenance/`:

| Manifest | Snapshot | sha256 of the manifest file |
|---|---|---|
| `provenance/CODE_MANIFEST_simulation_production.sha256` | simulation (all 16 run sets, BASE_SEED 41–43, 51–63) | `b20a64d84dcad210992f7d8d8a49497c79e2a4a108e8a4e1bb7eb9cea09abfe5` (= `code_manifest_sha256` in every chunk's `provenance.json`) |
| `provenance/CODE_MANIFEST_dataset_v3b.sha256` | dataset build v3b (scan, IBD/(α,n) event shards, **train**) | see file |
| `provenance/CODE_MANIFEST_dataset_v3e.sha256` | dataset build v3e (re-drawn **val/test** accidentals, merge) | see file |
| `provenance/CODE_MANIFEST_dataset_v3e_sub.sha256` | val/test subsample (seed 20261114) | see file |

**Build code shipped:** `dataset_build/tools/build_dataset.py` is the exact frozen v3e copy, sha256
`9fc7b8f6c326b85befdfd7727ae5155e99f0346a2e7b9b009c983c2ec541410d` (built val/test; also the version
`subsample_group.py` imports). `dataset_build/tools/build_dataset_v3b.py` is the exact frozen v3b copy, sha256
`b5e8a30328c94ff7de8d4b87c9967fea7a7ade28c0252cb00b8ab4f7d5d24317` (built the scan, the event shards and train).
To run the v3b one, copy it to `build_dataset.py` in a separate folder (the job scripts call it by that name).
Later development versions of `build_dataset.py` are NOT shipped.

**Not in the build snapshots:** `shuffle_eval_group.py` (sha256 `c5ae05b0…`, recorded in
`provenance/{val,test}_000.shuffle_manifest.json`) rewrote the built val/test files in a random order drawn from a
**secret 256-bit key that is not published** (publishing it would undo the shuffle). `verify_shuffled_group.py` is the
independent per-example check that the shuffled files hold byte-identical examples.

**Scrubbed copies:** a few job scripts contained cluster-specific paths (scratch file system, home-directory project
paths, Slurm account). They were replaced by environment variables (`PROJ`, `RUNS_ROOT`, `RATX_BIND`, `RATPAC_SIF`, `PY`);
nothing else changed. Their production sha256 is listed so the change is visible. Physics inputs (ratdb, macros,
generators, extractor, digitiser, builder) are byte-identical to production. Running from this folder therefore gives a
different `code_manifest_sha256` but the same physics `content_sha256` per chunk.

`extract_events.py` here is the production copy. A later local edit only added a two-line comment (the n–D elastic
scatter edge case, estimated ~5 × 10⁻⁴ per neutron) and is not shipped.

Files of the production snapshot that are NOT shipped: `ratdb/OBD17kt/IBD_GEO.ratdb` (never redistributed; regenerate it,
see `README.md`), the early BDT/feature tools (`tools/train_bdt.py`, `build_features.py`, `plot_bdt_results.py`,
`plot_v1_v2.py`, `analyze_energy_dependence.py`; not used for the dataset) and the v1-era jobs `geo_tests.sbatch`,
`variant_test.sbatch`, `install_ratpac.sbatch`, `obd_smoke.sbatch`, plus `env/obd-ml.local.freeze`.

| File in simulation/ | sha256 (this copy, first 16) | Production file | Status |
|---|---|---|---|
| `requirements-ml.txt` | `e063cb53a49a4b1d` | simulation snapshot `requirements-ml.txt` | identical |
| `dataset_build/jobs/build_dataset.sbatch` | `5b14bdbbb98f4098` | — | SCRUBBED EXAMPLE copy |
| `dataset_build/jobs/launch_v3_ds.sh` | `88075eab8588e10e` | — | SCRUBBED EXAMPLE copy |
| `dataset_build/jobs/launch_v3e.sh` | `decedff4dfd31b93` | — | SCRUBBED EXAMPLE copy |
| `dataset_build/jobs/subsample.sbatch` | `5a4b772798350dc6` | — | SCRUBBED EXAMPLE copy |
| `dataset_build/tools/build_dataset.py` | `9fc7b8f6c326b85b` | dataset build snapshot `tools/build_dataset.py` | v3b differs (b5e8a30328c9); v3e identical |
| `dataset_build/tools/build_dataset_v3b.py` | `b5e8a30328c94ff7` | dataset build snapshot `tools/build_dataset.py` | v3b identical |
| `dataset_build/tools/dataset_manifest.py` | `fc93210362224c3a` | dataset build snapshot `tools/dataset_manifest.py` | v3e identical |
| `dataset_build/tools/digitize.py` | `7fa570fb750532af` | dataset build snapshot `tools/digitize.py` | v3b identical; v3e identical |
| `dataset_build/tools/h5reader.py` | `ea11fcbfaa625750` | dataset build snapshot `tools/h5reader.py` | v3b identical; v3e identical |
| `dataset_build/tools/rates.py` | `b30be8d5cd181075` | dataset build snapshot `tools/rates.py` | v3b identical; v3e identical |
| `dataset_build/tools/shuffle_eval_group.py` | `c5ae05b003d01197` | dataset build snapshot `tools/shuffle_eval_group.py` | not in the build snapshots (used after the build; see notes) |
| `dataset_build/tools/subsample_group.py` | `fb5d3e6c54bbf6bf` | dataset build snapshot `tools/subsample_group.py` | v3e identical |
| `dataset_build/tools/train_stage1.py` | `74d99bb80632f06a` | dataset build snapshot `tools/train_stage1.py` | v3b identical; v3e identical |
| `dataset_build/tools/verify_shuffled_group.py` | `2b3b02aaefa2acdc` | dataset build snapshot `tools/verify_shuffled_group.py` | not in the build snapshots (used after the build; see notes) |
| `env/pins.sh` | `2eb153a603fca716` | simulation snapshot `env/pins.sh` | SCRUBBED copy (paths only); production sha256 f934d80f503660d7 |
| `jobs/repro_check.sbatch` | `154679e4645623ba` | simulation snapshot `jobs/repro_check.sbatch` | SCRUBBED copy (paths only); production sha256 098ade404fbb63dc |
| `jobs/run_chunk.sh` | `6856f8d815fa62aa` | simulation snapshot `jobs/run_chunk.sh` | SCRUBBED copy (paths only); production sha256 72f0b36f0e8240d8 |
| `jobs/run_chunk_local.sh` | `f292a0a5a0526a3c` | — | NEW for this repository |
| `jobs/sim_ibd_array.sbatch` | `e5b79cfcb2bb954a` | simulation snapshot `jobs/sim_ibd_array.sbatch` | SCRUBBED copy (paths only); production sha256 1bfef6ff59331d72 |
| `local_demo/check_materials.mac` | `68bc52eebe7d470a` | local demo (not part of production) | — |
| `local_demo/dump_event.py` | `1d6f2153858bb3f5` | local demo (not part of production) | — |
| `local_demo/export_views.mac` | `a80b237a5cce0e6e` | local demo (not part of production) | — |
| `local_demo/gui_demo.mac` | `b44eb8576c383eee` | local demo (not part of production) | — |
| `local_demo/ibd_demo_1event.mac` | `6f26d14ee9841b28` | local demo (not part of production) | — |
| `local_demo/plot_event.py` | `d9b3f148382bafea` | local demo (not part of production) | — |
| `local_demo/run_gui.sh` | `54df08221b49b928` | local demo (not part of production) | — |
| `local_demo/run_gui_apptainer.sh` | `616114a38beae623` | local demo (not part of production) | — |
| `local_demo/run_local.sh` | `d3b1025a86106efd` | local demo (not part of production) | — |
| `macros/alphan_hepevt.mac` | `0bb53a4eabd4c574` | simulation snapshot `macros/alphan_hepevt.mac` | identical |
| `macros/ibd_geo.mac` | `436602b19b2d8f7c` | simulation snapshot `macros/ibd_geo.mac` | identical |
| `macros/ibd_obd17kt.mac` | `2db5f5f68276fb39` | simulation snapshot `macros/ibd_obd17kt.mac` | identical |
| `macros/ibd_smoke_validation.mac` | `4e68ace89d0655a3` | simulation snapshot `macros/ibd_smoke_validation.mac` | identical |
| `macros/singles_decay0.mac` | `6934096ccfd1362a` | simulation snapshot `macros/singles_decay0.mac` | identical |
| `macros/singles_po210.mac` | `c1537dea542ac407` | simulation snapshot `macros/singles_po210.mac` | identical |
| `ratdb/OBD17kt/ENCAPSULATION_OBD.ratdb` | `b8c7f38a1f9baba5` | simulation snapshot `ratdb/OBD17kt/ENCAPSULATION_OBD.ratdb` | identical |
| `ratdb/OBD17kt/MATERIALS_OBD.ratdb` | `31eb9981acb9dea3` | simulation snapshot `ratdb/OBD17kt/MATERIALS_OBD.ratdb` | identical |
| `ratdb/OBD17kt/OBD17kt.geo` | `989ff236703b9a52` | simulation snapshot `ratdb/OBD17kt/OBD17kt.geo` | identical |
| `ratdb/OBD17kt/OPTICS_OBD.ratdb` | `84128bc2ccbc71cc` | simulation snapshot `ratdb/OBD17kt/OPTICS_OBD.ratdb` | identical |
| `ratdb/OBD17kt/PMTINFO_OBD17kt.ratdb` | `9ef25062726d1fc9` | simulation snapshot `ratdb/OBD17kt/PMTINFO_OBD17kt.ratdb` | identical |
| `ratdb/OBD17kt/PMT_OBD.ratdb` | `6005012000c5f677` | simulation snapshot `ratdb/OBD17kt/PMT_OBD.ratdb` | identical |
| `tools/extract_events.py` | `f9466bba97cd0ed7` | simulation snapshot `tools/extract_events.py` | identical |
| `tools/make_alphan_hepevt.py` | `d304a1100d815c33` | simulation snapshot `tools/make_alphan_hepevt.py` | identical |
| `tools/make_geo_ibd_spectrum.py` | `6fa61fff21dd210b` | simulation snapshot `tools/make_geo_ibd_spectrum.py` | identical |
| `tools/make_obd_ratdb.py` | `0bec44e60ce84518` | simulation snapshot `tools/make_obd_ratdb.py` | identical |
| `tools/make_pmt_layout.py` | `104b6c54419c5998` | simulation snapshot `tools/make_pmt_layout.py` | identical |
| `tools/timecmd.py` | `a12c61973c9f20e5` | simulation snapshot `tools/timecmd.py` | identical |
