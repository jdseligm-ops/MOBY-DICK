#!/bin/bash
# Run ONE production-identical simulation chunk on a workstation (no Slurm), via apptainer and jobs/run_chunk.sh.
#   usage: jobs/run_chunk_local.sh <out_dir> <BASE_SEED> <chunk_index> [nevents=200]
#   env:   MACRO, SPEC, ISOTOPE, VOLUME, LS_MATERIAL, SHIELD, LY exactly as in jobs/sim_ibd_array.sbatch / SEEDS.md
#          RATPAC_SIF (default $HOME/software/containers/ratpac-two_4.4.0.sif; sha256 is checked against env/pins.sh)
#          RATX_BIND  extra host path to bind into the container (only if <out_dir> is outside $HOME, the cwd and /tmp)
# Example (one geo-U chunk = production chunk 7 of run set geoU_gel_b41; needs ratdb/OBD17kt/IBD_GEO.ratdb first):
#   SHIELD=OBD_GLASS_SHIELD_GEL LY=10000.0 jobs/run_chunk_local.sh runs/geoU_gel_b41 41 7 200 geo_U238
# Writes <out_dir>/chunk_NNNNN/{*.events.npz, *.summary.json, provenance.json, SHA256SUMS, ...} and a frozen code
# snapshot in <out_dir>/code. Compare content_sha256 in provenance.json with the published chunk to check reproduction.
set -euo pipefail
OUT=$1; BASE_SEED=$2; TASK=$3; NEV=${4:-200}; SPEC=${5:-${SPEC:-default}}
PROJ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; export PROJ
command -v apptainer >/dev/null || { echo "apptainer not found (see README: container)"; exit 2; }
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
SEED=$(( BASE_SEED * 100000 + TASK ))
export CODE_PARENT="$OUT"
RUN="$OUT/chunk_$(printf %05d "$TASK")"
rm -rf "$RUN"
bash "$PROJ/jobs/run_chunk.sh" "$RUN" "$SEED" "$NEV" "$SPEC"
