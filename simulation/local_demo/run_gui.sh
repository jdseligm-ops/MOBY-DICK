#!/bin/bash
# Open ratpac-two's Geant4 Qt GUI (rat -g) for gui_demo.mac on the local X display; the macro exports PNG screenshots
# into the work directory and leaves the GUI open for interactive use. Usage: ./run_gui.sh <workdir> [seed]
set -euo pipefail
ROOTFS=${ROOTFS:-$HOME/software/containers/ratpac-two_4.4.0.rootfs}
HERE=$(cd "$(dirname "$0")" && pwd); GEO=$(cd "$HERE/.." && pwd)
W=$(realpath -m "$1"); SEED=${2:-20261114}; mkdir -p "$W"; cp -r "$GEO/ratdb/OBD17kt" "$W/"; cp "$HERE/gui_demo.mac" "$W/"
cd "$W"
bwrap --bind "$ROOTFS" / --dev /dev --dev-bind-try /dev/dri /dev/dri --proc /proc --tmpfs /tmp --bind /tmp/.X11-unix /tmp/.X11-unix \
      --ro-bind "${XAUTHORITY:-$HOME/.Xauthority}" /tmp/.Xauthority --bind "$W" "$W" --chdir "$W" \
      --ro-bind-try /etc/machine-id /etc/machine-id --ro-bind-try /etc/machine-id /var/lib/dbus/machine-id \
      --setenv XDG_RUNTIME_DIR /tmp/xdg --unsetenv DBUS_SESSION_BUS_ADDRESS \
      --setenv HOME "$W" --setenv DISPLAY "${DISPLAY:-:0}" --setenv XAUTHORITY /tmp/.Xauthority --setenv QT_X11_NO_MITSHM 1 --setenv LIBGL_ALWAYS_SOFTWARE 1 \
      --unsetenv LD_LIBRARY_PATH --unsetenv PYTHONPATH \
      /bin/bash -c 'mkdir -p -m 700 /tmp/xdg; for f in /.singularity.d/env/*.sh; do [ -r "$f" ] && . "$f"; done; exec /ratpac-setup/env.sh "$@"' _ \
      rat -g -s "$SEED" -o gui_demo.ntuple.root -l gui_rat.log gui_demo.mac
