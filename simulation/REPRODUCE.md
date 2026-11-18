# Reproduce a training set (step by step)

This is the exact path that produced the published files, scaled so that it can also run on one workstation.
Paths are relative to this `simulation/` folder. Costs measured in production: 2.5–4.6 s per event (one CPU, ~1.4 GB
RSS per `rat` process); raw ntuple ~570 KB/event, `events.npz` ~15 KB/event.

## 0. Requirements

- Linux x86_64 with **apptainer** (≥ 1.2; 1.5.5 tested). Without apptainer, `local_demo/run_local.sh` runs the same image
  with `unsquashfs` + `bwrap`.
- ~3 GB for the container, plus disk for outputs.
- Host Python for the dataset build: numpy, scipy, h5py, scikit-learn (production pins in `requirements-ml.txt`;
  `train_stage1.py` imports scikit-learn at module level, so it must be installed even though only `split_of` is used).

```bash
python3 -m venv .venv-build && . .venv-build/bin/activate
pip install numpy==2.5.4 scipy==1.18.1 scikit-learn==1.9.1 h5py
```

## 1. Get the container (pinned by digest)

```bash
mkdir -p ~/software/containers
apptainer pull ~/software/containers/ratpac-two_4.4.0.sif docker://ratpac/ratpac-two@sha256:c85936d537dba4adba050c9fe4dde45a44e57454579ac96756007a925ff4c626
sha256sum ~/software/containers/ratpac-two_4.4.0.sif | tee ~/software/containers/ratpac-two_4.4.0.sif.sha256
```

If the hash differs from `RATPAC_SIF_SHA256` in `env/pins.sh` (production `3b6cc869…`), `run_chunk.sh` refuses to run.
Either use the production SIF or set `RATPAC_SIF_SHA256` to your own image's hash and record that you did.
Use `RATPAC_SIF=/path/to.sif` for another location.

## 2. Make the geo-ν spectrum table (only for geo-U / geo-Th IBD)

```bash
python3 tools/make_geo_ibd_spectrum.py --check   # pinned-sha256 download; writes ratdb/OBD17kt/IBD_GEO.ratdb
```

Expect table sha256 `2b3a7e13…` (full value in `README.md`). See `README.md` for the fallback if the download fails.

## 3. Simulate chunks

One chunk = 200 events with seed `BASE_SEED*100000 + chunk` (`SEEDS.md`). The settings per run set are in `SEEDS.md`
and `provenance/production_runsets.json`. All production chunks used:

```bash
export SHIELD=OBD_GLASS_SHIELD_GEL LY=10000.0 LS_MATERIAL=obd_ls_li6_1p0
```

**Locally, one chunk at a time** (`jobs/run_chunk_local.sh <out_dir> <BASE_SEED> <chunk> [nev] [spectrum]`):

```bash
# geo-U IBD, chunk 7 of run set geoU_gel_b41 (seed 4100007; seed % 10 = 7 -> train outside the wedges)
MACRO=ibd_geo jobs/run_chunk_local.sh runs/geoU_gel_b41 41 7 200 geo_U238
# reactor IBD (stock spectrum)
MACRO=ibd_geo jobs/run_chunk_local.sh runs/reactor_gel_b43 43 0 200 default
# 13C(alpha,n)16O
MACRO=alphan_hepevt jobs/run_chunk_local.sh runs/alphan_gel_b51 51 0 200
# 210Po alpha singles
MACRO=singles_po210 jobs/run_chunk_local.sh runs/po210_ls_gel_b52 52 0 200
# Decay0 singles: acrylic Bi-214, LS BiPo-214, ...
MACRO=singles_decay0 ISOTOPE=Bi214 VOLUME='^acrylic_vessel$' jobs/run_chunk_local.sh runs/bi214_acrylic_gel_b54 54 0 200
MACRO=singles_decay0 ISOTOPE=BiPo214 VOLUME='^scintillator$' jobs/run_chunk_local.sh runs/bipo214_ls_gel_b58 58 0 200
```

Each chunk folder gets `<sample>_s<seed>.events.npz` (the per-PE table the dataset is built from), `.summary.json`,
`.rndm_states.tar` (per-event RNG states), `run.mac`, `provenance.json` and `SHA256SUMS`. The run-set folder gets a frozen
`code/` snapshot; a chunk aborts if the live folder changes while a run set is in progress.

**Check that you reproduced production:** the `content_sha256` in `provenance.json` is a hash of the extracted physics
arrays. For the same seed, NEV and settings it must equal the production value (identical across five CPU generations
in our tests). Production `content_sha256` values are listed per chunk in the authors' archive; e.g. `po210_ls_gel_b52`
chunk 0 (seed 5200000) = `8efb830461bfcce258704690bee19cbebae58d3fb984ed5700d0efc246d75c9c`.
Verified 2026-11-17: `MACRO=singles_po210 jobs/run_chunk_local.sh … 52 0 200` from this folder, on a 12th-gen Intel
Core laptop with the production SIF, reproduced this hash exactly (production ran on a cluster Xeon node).
`code_manifest_sha256` will differ from production if you run from this folder, because a few job scripts were scrubbed
of cluster paths (`CODE_PROVENANCE.md`).

**On a Slurm cluster** (example; edit partition/account, `mkdir logs` first):

```bash
export PROJ=$PWD RUNS_ROOT=/your/scratch/runs
sbatch --array=0-499%200 --export=ALL,BASE_SEED=41,NEV=200,TAG=geoU_gel,SPEC=geo_U238,MACRO=ibd_geo,SHIELD=$SHIELD,LY=$LY jobs/sim_ibd_array.sbatch
sbatch --array=0-149     --export=ALL,BASE_SEED=54,NEV=200,TAG=bi214_acrylic_gel,MACRO=singles_decay0,ISOTOPE=Bi214,VOLUME='^acrylic_vessel$',SHIELD=$SHIELD,LY=$LY jobs/sim_ibd_array.sbatch
```

Use a **new, unused BASE_SEED** for new events (`SEEDS.md` lists the used ones). One run set = one variant.

## 4. Build the dataset

Run from `dataset_build/tools` (the scripts import each other by module name). `B=build_dataset.py` below is the frozen
v3e copy; to reproduce the published **train** files byte for byte, use `build_dataset_v3b.py` (renamed to
`build_dataset.py` in a separate folder) for steps 4a–4d, exactly as v3b was built.

```bash
cd dataset_build/tools
OUT=../../ds_mine; mkdir -p $OUT/scan $OUT/shards $OUT/final
G=../../runs          # where the chunk folders are
# 4a. scan every singles chunk: does each decay trigger alone? vertex, split (sample tags as in rates.py)
for f in $G/bi214_acrylic_gel_b54/chunk_*/*.events.npz; do
  python3 build_dataset.py scan --chunk $f --sample bi214_acrylic -o $OUT/scan/bi214_acrylic__$(basename $f .events.npz).scan.npz; done
#     (repeat for po210_ls, k40_acrylic, tl208_acrylic, and the LS singles pa234m_ls pb214_ls bipo214_ls ac228_ls pb212_ls bipo212_ls tl208_ls k40_ls)
# 4b. IBD / (alpha,n) events -> one example per event (tags geoU, geoTh, reactor, alphan)
for f in $G/geoU_gel_b41/chunk_*/*.events.npz; do
  python3 build_dataset.py events --chunk $f --sample geoU -o $OUT/shards/geoU__$(basename $f .events.npz); done
# 4c. accidental pairs per split (train as in v3b: 40 tasks, 120,000 pairs in total)
for t in $(seq 0 39); do
  python3 build_dataset.py accidentals --scan-dir $OUT/scan --split train --task $t --n-tasks 40 --budget 120000 \
          -o $OUT/shards/acc_train_$(printf %03d $t); done
# 4d. merge shards into final files with yearly weights
python3 build_dataset.py merge --shard-dir $OUT/shards --group train -o $OUT/final
python3 build_dataset.py geometry --chunk <any .events.npz> -o $OUT/final/pmt_geometry.h5
python3 dataset_manifest.py $OUT          # md5 manifest + accidental pair plans
```

Validation/test as published (v3e): accidentals with `--split val_random|val_wedge|test_random|test_wedge --n-tasks 60
--budget 100000 --dt-mix 0.6 --dt-tau 5300`, then `merge --group val|test`, then

```bash
python3 subsample_group.py --group val --in-dir $OUT/final --out-dir $OUT/sub \
  --acc-alloc '{"0-1.5":300,"1.5-3":300,"3-4.5":300,"4.5-6":300,"6-9":1200,"9-12":1800,"12-20":5200,"20-1e+09":8600}'
python3 shuffle_eval_group.py --wave $OUT/sub/val_000.h5 --labels $OUT/sub/val_000.labels.h5 --out-dir $OUT/shuffled --private-dir $OUT/PRIVATE
python3 verify_shuffled_group.py --help    # independent per-example check of the shuffle
```

The exact production chunk lists, task counts and job chaining are in `dataset_build/jobs/launch_v3_ds.sh` (v3b) and
`launch_v3e.sh` (v3e), with `build_dataset.sbatch` and `subsample.sbatch` (Slurm examples; set `PROJ=<path>/dataset_build`).

Notes:
- **Weights** are computed in `merge` from the simulated counts of the chunks you actually provide: IBD/(α,n)
  `rate / n_simulated(class, split)`; accidentals `N_ij · importance / M_ij` with `N_ij` from `rates.py` activities × the
  trigger fractions measured by your scan. A smaller simulation gives the same yearly totals with fewer examples.
- **Splits** come from the chunk seed and the prompt vertex φ (`SEEDS.md`), so a new set built from new BASE_SEEDs keeps
  the same split rule. Singles are split before pairing; no decay enters two splits.
- **Exact byte reproduction** of the published IBD/(α,n) examples needs only the same chunk (seed, evid) and digi seed
  (RNG key `[1, 7, seed, evid]`). Published accidentals additionally need the identical scan inventory, task count and
  budget, because their RNG keys include the task and shard index.
- The val/test **storage order** of the published files comes from a secret key that is not released; your own shuffle
  will give a different order (examples identical).
- Production memory: merge and subsample of val/test used up to 120 GB RAM; scan/events/accidentals tasks 8 GB each.

## 5. Use it

The files have the published format (`DATASET.md` §2–§6) and work directly with the baseline in `../baseline/`.
