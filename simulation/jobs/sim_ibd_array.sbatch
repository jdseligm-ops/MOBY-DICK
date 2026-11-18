#!/bin/bash
# OBD17kt_geo variant (2026-11-13, copied from projects/OBD17kt): same chunking/seed scheme; the sample is chosen by
# env MACRO / SPEC / ISOTOPE / VOLUME / LS_MATERIAL (see jobs/run_chunk.sh), e.g.
#   sbatch --array=0-199%200 --export=ALL,BASE_SEED=11,NEV=200,TAG=geoU,SPEC=geo_U238 jobs/sim_ibd_array.sbatch
#   sbatch --array=0-99 --export=ALL,BASE_SEED=21,NEV=500,TAG=bi214_shield,MACRO=singles_decay0,ISOTOPE=Bi214,VOLUME='_dome_encapsulation_phys$' jobs/sim_ibd_array.sbatch
# Production: one array task = one chunk = one rat process with its own seed.
#   seed = BASE_SEED * 100000 + SLURM_ARRAY_TASK_ID   (unique, recorded per event in the .events.npz)
# Size the array from the smoke-test timing, e.g. 200 events/chunk:
#   sbatch --array=0-999%200 --export=ALL,BASE_SEED=1,NEV=200,TAG=pilot jobs/sim_ibd_array.sbatch
# Model variant via env (recorded per chunk): SHIELD=OBD_GLASS_SHIELD_GEL LY=7240.0  (defaults: air, 10000.0)
# Every run set (TAG,BASE_SEED) must use ONE variant; BASE_SEED must be unique across all run sets.
#SBATCH --job-name=obd-geo
##SBATCH --account=<your_account>   # site-specific (production: the cluster's default account)
#SBATCH --partition=kill-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=04:00:00
#SBATCH --requeue
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail
# [GitHub copy: EXAMPLE for a Slurm site. Cluster paths/account scrubbed; set PROJ and RUNS_ROOT, mkdir logs/ first.]
: "${SLURM_ARRAY_TASK_ID:?submit as an array}"
BASE_SEED=${BASE_SEED:?set BASE_SEED}; NEV=${NEV:-200}; TAG=${TAG:-prod}; SPEC=${SPEC:-default}
SEED=$(( BASE_SEED * 100000 + SLURM_ARRAY_TASK_ID ))
PARENT="${RUNS_ROOT:?set RUNS_ROOT to a large scratch directory}/OBD17kt_geo/${TAG}_b${BASE_SEED}"
RUN="$PARENT/chunk_$(printf %05d "$SLURM_ARRAY_TASK_ID")"
export CODE_PARENT="$PARENT"     # one frozen code snapshot shared by all tasks of this run set
# a requeued (pre-empted) task restarts its chunk from scratch with the same seed -> identical events
rm -rf "$RUN"
bash "${PROJ:?set PROJ to the simulation/ folder}/jobs/run_chunk.sh" "$RUN" "$SEED" "$NEV" "$SPEC"
