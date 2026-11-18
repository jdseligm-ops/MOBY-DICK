#!/bin/bash
# Run ratpac-two 4.4.0 (the exact container used for the OBD 17 kt production on the HPC cluster) on a workstation without root or
# apptainer: unpack the SIF's squashfs once, then run inside a bubblewrap sandbox.
#   ./run_local.sh <macro.mac> <seed> <out.ntuple.root>
# Needs: unsquashfs (squashfs-tools), bwrap (bubblewrap), unprivileged user namespaces; ~9 GB disk for the unpacked image.
set -euo pipefail
SIF=${SIF:-$HOME/software/containers/ratpac-two_4.4.0.sif}
ROOTFS=${ROOTFS:-$HOME/software/containers/ratpac-two_4.4.0.rootfs}
HERE=$(cd "$(dirname "$0")" && pwd); GEO=$(cd "$HERE/.." && pwd)
MAC=$(realpath "$1"); SEED=$2; OUT=$3
if [[ ! -d "$ROOTFS/ratpac-setup" ]]; then
  off=$(grep -obUaP "hsqs" "$SIF" | head -1 | cut -d: -f1)        # SIF stores the root filesystem as one squashfs partition
  echo "unpacking $SIF (squashfs at byte $off) -> $ROOTFS"
  unsquashfs -q -o "$off" -d "$ROOTFS" "$SIF"
fi
WORK=$(dirname "$(realpath -m "$OUT")"); mkdir -p "$WORK"
cp -r "$GEO/ratdb/OBD17kt" "$WORK/"                                  # detector description (same files as production)
cp "$MAC" "$WORK/run.mac"
cd "$WORK"
bwrap --bind "$ROOTFS" / --dev /dev --proc /proc --tmpfs /tmp --bind "$WORK" "$WORK" --ro-bind "$HERE" "$HERE" --chdir "$WORK" \
      --setenv HOME "$WORK" --unsetenv LD_LIBRARY_PATH --unsetenv PYTHONPATH \
      /bin/bash -c 'for f in /.singularity.d/env/*.sh; do [ -r "$f" ] && . "$f"; done; exec /ratpac-setup/env.sh "$@"' _ \
      rat -s "$SEED" -o "$(basename "$OUT")" -l rat.log run.mac
