#!/bin/bash
# v3e val/test (plan PLAN_SELECTION_PHYSICS.md A1'): re-draw ONLY the val/test accidental pairs with importance-sampled dt
# (q = 0.6 Exp(5.3 us) + 0.4 U(0,50 us), weight x u/q), 100k pairs per sub-split; reuse the v3b scan and event shards.
# Then merge val/test and subsample with the doubled per-bin allocation. Run on a Slurm login node (bash + sbatch only).
# [GitHub copy: cluster paths scrubbed (RUNS_ROOT, PROJ). The sbatch scripts are EXAMPLES.]
set -euo pipefail
ML=${RUNS_ROOT:?set RUNS_ROOT}/OBD17kt_ml; V3B=$ML/dataset_v3b; OUT=$ML/dataset_v3e
cd "${PROJ:?set PROJ to simulation/dataset_build}"
mkdir -p "$OUT/shards" "$OUT/final"
[[ -e "$OUT/scan" ]] || ln -s "$V3B/scan" "$OUT/scan"
for f in "$V3B"/shards/*; do b=$(basename "$f"); [[ "$b" == acc_* ]] && continue; [[ -e "$OUT/shards/$b" ]] || ln -s "$f" "$OUT/shards/$b"; done
NT=60; A=""
for s in val_random val_wedge test_random test_wedge; do
  j=$(sbatch --parsable --array=0-$((NT-1)) --job-name=obd-v3e-acc --export=ALL,MODE=accidentals,OUT=$OUT,SPLIT=$s,NTASKS=$NT,BUDGET=100000,DT_MIX=0.6,DT_TAU=5300 jobs/build_dataset.sbatch)
  A="$A:$j"; echo "v3e accidentals $s $j"
done
export ALLOC='{"0-1.5":300,"1.5-3":300,"3-4.5":300,"4.5-6":300,"6-9":1200,"9-12":1800,"12-20":5200,"20-1e+09":8600}'
for g in val test; do
  m=$(sbatch --parsable -p kill-shared -c 4 --mem=120G --time=04:00:00 --job-name=obd-v3e-merge --dependency=afterok${A} --export=ALL,MODE=merge,OUT=$OUT,GROUP=$g jobs/build_dataset.sbatch)
  s2=$(sbatch --parsable --mem=120G --job-name=obd-v3e-sub --dependency=afterok:$m --export=ALL,GROUP=$g,IN=$OUT/final,OUT=$ML/dataset_v3e_sub jobs/subsample.sbatch)
  echo "v3e merge $g $m subsample $s2"
done
echo "$(date -Is) v3e launched (dt-mix 0.6 tau 5300, 100k/sub-split, alloc $ALLOC)" >> $ML/job_receipts.log
