#!/bin/bash
# DATASET part only (v3b: rerun after the NEV_PER_CHUNK bug killed dataset_v3).
# Launch the complete v3 rebuild on the GEL / fixed-optics production (BASE_SEED 41-63, TAG suffix _gel).
# Run on a Slurm login node (it only builds chunk lists and calls sbatch):  PROJ=<simulation/dataset_build> RUNS_ROOT=<scratch> bash jobs/launch_v3_ds.sh
# Prints every job id; record them in a job-receipts log.
# [GitHub copy: cluster paths scrubbed (RUNS_ROOT, PROJ). The sbatch scripts are EXAMPLES.]
# Chains (dependencies via afterok):
#   dataset_v3: scan -> accidentals (5 splits) ; events ; merges train/val/test/dev
#   stage1_v3 : rows (chunk ids 0-39 / 0-19 ...) -> train (+diag) -> threshold (in stage2_v3) -> stage2 rows (ids 100-199 / 50-99 ...) -> stage2 train
#   dist_v3   : rows (ids 200-299 / 100-149 ...) -> train -> tri (ids 100-149 / 50-74 ..., val/test splits only)
set -euo pipefail
R=${RUNS_ROOT:?set RUNS_ROOT}
G=$R/OBD17kt_geo
ML=$R/OBD17kt_ml
cd "${PROJ:?set PROJ to simulation/dataset_build}"

add() {  # add <listfile> <tag> <runset> <from> <to>
  local f=$1 tag=$2 set=$3 a=$4 b=$5 i x
  for i in $(seq "$a" "$b"); do x=$(ls "$G/$set/chunk_$(printf %05d "$i")"/*.events.npz 2>/dev/null | head -1); [[ -n "$x" ]] && echo "$tag $x" >> "$f"; done
}
LS="pa234m pb214 bipo214 ac228 pb212 bipo212 tl208 k40"

# ---------------- dataset v3 ----------------
DS=$ML/dataset_v3b; mkdir -p "$DS"; S=$DS/singles.list; E=$DS/events.list; : > "$S"; : > "$E"
for set in po210_ls_gel_b52 k40_acrylic_gel_b53 bi214_acrylic_gel_b54 tl208_acrylic_gel_b55; do tag=${set%_gel_b*}; for f in "$G/$set"/chunk_*/*.events.npz; do echo "$tag $f" >> "$S"; done; done
for t in $LS; do s=$(ls -d "$G/${t}_ls_gel_b"* | head -1); for f in "$s"/chunk_*/*.events.npz; do echo "${t}_ls $f" >> "$S"; done; done
for set in geoU_gel_b41 geoTh_gel_b42 reactor_gel_b43 alphan_gel_b51; do tag=${set%_gel_b*}; for f in "$G/$set"/chunk_*/*.events.npz; do echo "$tag $f" >> "$E"; done; done
NS=$(( ($(wc -l < "$S") + 9) / 10 - 1 )); NE=$(( ($(wc -l < "$E") + 4) / 5 - 1 ))
J1=$(sbatch --parsable --array=0-$NS%100 --export=ALL,MODE=scan,LIST=$S,OUT=$DS,K=10 jobs/build_dataset.sbatch)
J2=$(sbatch --parsable --array=0-$NE%150 --export=ALL,MODE=events,LIST=$E,OUT=$DS,K=5 jobs/build_dataset.sbatch)
A=""
for sp in train:40:120000 val_random:15:50000 val_wedge:15:50000 test_random:15:50000 test_wedge:15:50000; do
  IFS=: read -r s nt b <<< "$sp"
  j=$(sbatch --parsable --array=0-$((nt-1)) --dependency=afterok:$J1 --export=ALL,MODE=accidentals,OUT=$DS,SPLIT=$s,NTASKS=$nt,BUDGET=$b jobs/build_dataset.sbatch)
  A="$A:$j"; echo "dataset_v3 accidentals $s $j"
done
for g in train val test dev; do
  m=$(sbatch --parsable -p sandbox -c 8 --mem=32G --time=04:00:00 --dependency=afterok:$J2$A --export=ALL,MODE=merge,OUT=$DS,GROUP=$g jobs/build_dataset.sbatch)
  echo "dataset_v3 merge $g $m"
done
echo "dataset_v3 scan $J1 events $J2"

