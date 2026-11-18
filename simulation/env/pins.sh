# [GitHub copy: the cluster scratch bind path was replaced by env RATX_BIND, and RATPAC_SIF is overridable.]
# Pinned inputs for every OBD17kt job (sourced by jobs/*). Change only deliberately; record why in docs.
RATPAC_TAG=4.4.0
RATPAC_DIGEST=sha256:c85936d537dba4adba050c9fe4dde45a44e57454579ac96756007a925ff4c626   # docker hub, linux/amd64, 2026-10-11
RATPAC_SIF="${RATPAC_SIF:-$HOME/software/containers/ratpac-two_${RATPAC_TAG}.sif}"   # override with env RATPAC_SIF
# sha256 of the built SIF; filled in after the install job (empty = not yet pinned -> jobs compute and record it)
RATPAC_SIF_SHA256=3b6cc869a0b17db116a5e2d751b7f6ac534714a5f25e5f00810ff3d6c4d3ecba   # built 2026-11-12 by job 15397926

# Run a command inside the ratpac container WITH its environment. Uses `apptainer exec` + the image's own
# /ratpac-setup/env.sh instead of `apptainer run`, whose OCI runscript re-evaluates arguments through a shell
# (it expanded $(...) too early and choked on parentheses in job 15397926). --cleanenv keeps host env out.
ratx() { apptainer exec --cleanenv ${RATX_BIND:+--bind "$RATX_BIND"} ${RATX_OPTS:-} "$RATPAC_SIF" /ratpac-setup/env.sh "$@"; }
