#!/bin/bash
# ratpac-two GUI (rat -g, Geant4 Qt) through apptainer on the local display.  Usage: ./run_gui_apptainer.sh <workdir> [seed]
set -euo pipefail
SIF=${SIF:-$HOME/software/containers/ratpac-two_4.4.0.sif}
HERE=$(cd "$(dirname "$0")" && pwd); GEO=$(cd "$HERE/.." && pwd)
W=$(realpath -m "$1"); SEED=${2:-20261114}; mkdir -p "$W"
cp -r "$GEO/ratdb/OBD17kt" "$W/"; cp "$HERE/gui_demo.mac" "$HERE/export_views.mac" "$W/"
cd "$W"
apptainer exec --bind "$W" --bind /etc/machine-id:/etc/machine-id:ro --bind /etc/machine-id:/var/lib/dbus/machine-id:ro --bind "/run/user/$(id -u)" "$SIF" /ratpac-setup/env.sh rat -g -s "$SEED" -o gui_demo.ntuple.root -l gui_rat.log gui_demo.mac
