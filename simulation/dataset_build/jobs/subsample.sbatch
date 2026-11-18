#!/bin/bash
# Smaller val/test group from a full build (tools/subsample_group.py). Code frozen into $OUT/code.
#   sbatch --export=ALL,GROUP=val,IN=<dir>,OUT=<dir>,ALLOC='<json>' jobs/subsample.sbatch
#SBATCH --job-name=obd-subsample
##SBATCH --account=<your_account>   # site-specific (production: the cluster's default account)
#SBATCH --partition=kill-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
# [GitHub copy: EXAMPLE for a Slurm site. Cluster paths/account/env path scrubbed; set PROJ (and PY), mkdir logs/ first.]
: "${GROUP:?}" "${IN:?}" "${OUT:?}" "${ALLOC:?}"
PROJ="${PROJ:?set PROJ to simulation/dataset_build}"; PY="${PY:-python3}"   # production: a conda env with requirements-ml.txt + h5py
mkdir -p "$OUT/final"
if [[ ! -d "$OUT/code" ]]; then
  tmp=$(mktemp -d "$OUT/.code.XXXXXX"); cp -r "$PROJ/tools" "$tmp/"
  (cd "$tmp" && find . -type f ! -path '*/__pycache__/*' -print0 | sort -z | xargs -0 sha256sum > CODE_MANIFEST.sha256)
  mv -T "$tmp" "$OUT/code" 2>/dev/null || rm -rf "$tmp"
fi
cd "$OUT/code/tools"
"$PY" subsample_group.py --group "$GROUP" --in-dir "$IN" --out-dir "$OUT/final" --acc-alloc "$ALLOC"
echo SUBSAMPLE_DONE "$GROUP"
