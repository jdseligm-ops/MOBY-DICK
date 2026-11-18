#!/bin/bash
# Cross-CPU reproducibility: rerun the smoke seed (10 events) on a different CPU generation and compare
# content_sha256 with the smoke run. Submit once per CPU type, e.g.
#   sbatch --constraint=cascade_lake jobs/repro_check.sbatch
#   sbatch --constraint=ice_lake     jobs/repro_check.sbatch
# If all hashes match, production can use any node type; otherwise pin production to one --constraint.
#SBATCH --job-name=obd-repro
##SBATCH --account=<your_account>   # site-specific (production: the cluster's default account)
#SBATCH --partition=shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=04:00:00
#SBATCH --no-requeue
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
# [GitHub copy: EXAMPLE for a Slurm site. Cluster paths/account scrubbed; set PROJ and RUNS_ROOT, mkdir logs/ first.]
: "${SLURM_JOB_ID:?must run inside Slurm}"
RUN="${RUNS_ROOT:?set RUNS_ROOT to a large scratch directory}/OBD17kt/$(date +%Y%m%d)_repro_${SLURM_JOB_ID}"
bash "${PROJ:?set PROJ to the simulation/ folder}/jobs/run_chunk.sh" "$RUN" 20261112 10 default
echo "cpu: $(lscpu | sed -n 's/^Model name:[[:space:]]*//p' | head -1)"
grep -o '"content_sha256": "[0-9a-f]*"' "$RUN/provenance.json"
