#!/bin/bash
# Hackathon dataset build (tools/build_dataset.py). Code is frozen into $OUT/code on first use.
#   scan        : sbatch --array=0-N --export=ALL,MODE=scan,LIST=<singles list>,OUT=<dir>,K=10 jobs/build_dataset.sbatch
#   events      : sbatch --array=0-N --export=ALL,MODE=events,LIST=<ibd/alphan list>,OUT=<dir>,K=5 jobs/build_dataset.sbatch
#   accidentals : sbatch --array=0-(NT-1) --export=ALL,MODE=accidentals,OUT=<dir>,SPLIT=train,NTASKS=NT,BUDGET=B jobs/build_dataset.sbatch
#   merge       : sbatch -p sandbox -c 2 --mem=60G --export=ALL,MODE=merge,OUT=<dir>,GROUP=train jobs/build_dataset.sbatch
# Layout: $OUT/scan/*.scan.npz, $OUT/shards/*.h5 + *.truth.npz, $OUT/final/<group>_NNN.h5 + .labels.h5
#SBATCH --job-name=obd-ds
##SBATCH --account=<your_account>   # site-specific (production: the cluster's default account)
#SBATCH --partition=kill-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=04:00:00
#SBATCH --requeue
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail
# [GitHub copy: EXAMPLE for a Slurm site. Cluster paths/account/env path scrubbed; set PROJ (and PY), mkdir logs/ first.]
: "${MODE:?}" "${OUT:?}"
PROJ="${PROJ:?set PROJ to simulation/dataset_build}"
PY="${PY:-python3}"   # production: a conda env with requirements-ml.txt + h5py
mkdir -p "$OUT/scan" "$OUT/shards" "$OUT/final"
if [[ ! -d "$OUT/code" ]]; then
  tmp=$(mktemp -d "$OUT/.code.XXXXXX"); cp -r "$PROJ/tools" "$tmp/"
  (cd "$tmp" && find . -type f ! -path '*/__pycache__/*' -print0 | sort -z | xargs -0 sha256sum > CODE_MANIFEST.sha256)
  mv -T "$tmp" "$OUT/code" 2>/dev/null || rm -rf "$tmp"
fi
B="$OUT/code/tools/build_dataset.py"
case "$MODE" in
  scan|events)
    : "${LIST:?}" "${SLURM_ARRAY_TASK_ID:?}"
    K=${K:-5}; start=$(( SLURM_ARRAY_TASK_ID * K ))
    sed -n "$((start + 1)),$((start + K))p" "$LIST" | while read -r tag path; do
      base="${tag}__$(basename "$path" .events.npz)"
      if [[ "$MODE" == scan ]]; then
        [[ -s "$OUT/scan/$base.scan.npz" ]] && continue
        "$PY" "$B" scan --chunk "$path" --sample "$tag" -o "$OUT/scan/$base.tmp.npz" && mv "$OUT/scan/$base.tmp.npz" "$OUT/scan/$base.scan.npz"
      else
        [[ -s "$OUT/shards/$base.h5" && -s "$OUT/shards/$base.truth.npz" ]] && continue
        "$PY" "$B" events --chunk "$path" --sample "$tag" -o "$OUT/shards/$base"
      fi
    done ;;
  accidentals)
    : "${SPLIT:?}" "${NTASKS:?}" "${BUDGET:?}" "${SLURM_ARRAY_TASK_ID:?}"
    base="acc_${SPLIT}_$(printf %03d "$SLURM_ARRAY_TASK_ID")"
    "$PY" "$B" accidentals --scan-dir "$OUT/scan" --split "$SPLIT" --task "$SLURM_ARRAY_TASK_ID" --n-tasks "$NTASKS" --budget "$BUDGET" --dt-mix "${DT_MIX:-0}" --dt-tau "${DT_TAU:-5300}" -o "$OUT/shards/$base" ;;
  merge)
    : "${GROUP:?}"
    "$PY" "$B" merge --shard-dir "$OUT/shards" --group "$GROUP" -o "$OUT/final" ;;
esac
echo "DS_OK $MODE ${SLURM_ARRAY_TASK_ID:-} ${SPLIT:-}${GROUP:-} $(date -Is)"
