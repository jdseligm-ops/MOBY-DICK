#!/bin/bash
# Simulate one chunk of events in OBD 17 kt and extract the ML table. Called by the sbatch scripts.
# OBD17kt_geo variant (2026-11-13, copied from projects/OBD17kt): the macro, LS material and generator settings are
# parameters (all recorded in provenance.json):
#   env MACRO        ibd_geo (default) | singles_decay0 | singles_po210 | alphan_hepevt   (macros/<MACRO>.mac)
#   env LS_MATERIAL  obd_ls_li6_1p0 (default, 1.0 wt% 6Li) | obd_ls_li6 (0.1 wt%)
#   [spectrum]       IBD spectrum index for ibd_geo: geo_U238 | geo_Th232 | default (reactor)
#   env ISOTOPE, VOLUME   for singles_decay0 (Decay0 isotope, regex on physical-volume names)
# usage: run_chunk.sh <run_dir> <seed> <nevents> [spectrum]
#   env CODE_PARENT  directory holding the frozen code snapshot for this run set (default: <run_dir>)
#   env FULL_SIF_CHECK=1  hash the whole container image (slow, ~3 GB read) instead of trusting <sif>.sha256
#
# Reproducibility contract: every chunk records the container digest + image sha256, a sha256 manifest of
# every code/config file used, the seed, node CPU model, and a content hash of the extracted physics arrays.
# The chunk runs from the frozen snapshot, never from the live project tree, and aborts if the live tree
# differs from the snapshot (i.e. code changed while an array was running).
set -euo pipefail
# [GitHub copy: only the PROJ default and an unused cluster scratch variable differ from the production file;
#  see ../CODE_PROVENANCE.md. Bind extra host paths into the container with env RATX_BIND.]
RUN_DIR=$1; SEED=$2; NEV=$3; SPEC=${4:-default}
SHIELD=${SHIELD:-OBD_GLASS_SHIELD}     # env: ENCAPSULATION model for the PMT shields (recorded in provenance)
LY=${LY:-10000.0}                      # env: LS light yield, photons/MeV (recorded in provenance)
MACRO=${MACRO:-ibd_geo}
LS_MATERIAL=${LS_MATERIAL:-obd_ls_li6_1p0}
ISOTOPE=${ISOTOPE:-}; VOLUME=${VOLUME:-}
case "$MACRO" in
  ibd_geo)        MODE=ibd;     SAMPLE="ibd_${SPEC}" ;;
  singles_decay0) MODE=generic; SAMPLE="decay0_${ISOTOPE}"
                  [[ -n "$ISOTOPE" && -n "$VOLUME" ]] || { echo "singles_decay0 needs ISOTOPE and VOLUME"; exit 2; } ;;
  singles_po210)  MODE=generic; SAMPLE="po210" ;;
  alphan_hepevt)  MODE=generic; SAMPLE="alphan" ;;
  *) echo "unknown MACRO=$MACRO"; exit 2 ;;
esac
PROJ="${PROJ:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"   # the simulation/ folder (GitHub copy: was a cluster home path)
source "$PROJ/env/pins.sh"
SIF="$RATPAC_SIF"
CODE_PARENT=${CODE_PARENT:-$RUN_DIR}
[[ -s "$SIF" ]] || { echo "missing $SIF: run jobs/install_ratpac.sbatch first"; exit 2; }
START=$(date -Is)

# ---- frozen code snapshot (made once per run set; atomic rename so parallel tasks agree) ----------------
manifest() { (cd "$1" && find env jobs macros ratdb tools requirements-ml.txt -type f ! -path '*/__pycache__/*' -print0 \
              | sort -z | xargs -0 sha256sum); }
mkdir -p "$CODE_PARENT"
if [[ ! -d "$CODE_PARENT/code" ]]; then
  tmp=$(mktemp -d "$CODE_PARENT/.code.XXXXXX")
  (cd "$PROJ" && cp -r --parents env jobs macros ratdb tools requirements-ml.txt "$tmp/")
  find "$tmp" -name __pycache__ -prune -exec rm -rf {} +
  manifest "$tmp" > "$tmp/CODE_MANIFEST.sha256"
  mv -T "$tmp" "$CODE_PARENT/code" 2>/dev/null || rm -rf "$tmp"   # another task won the race: use theirs
fi
CODE="$CODE_PARENT/code"
manifest "$PROJ" | diff -q - "$CODE/CODE_MANIFEST.sha256" >/dev/null \
  || { echo "ABORT: live project differs from the frozen snapshot in $CODE (code changed mid-run)"; exit 3; }
CODE_HASH=$(sha256sum "$CODE/CODE_MANIFEST.sha256" | cut -d' ' -f1)

# ---- container identity --------------------------------------------------------------------------------
if [[ "${FULL_SIF_CHECK:-0}" == 1 || ! -s "$SIF.sha256" ]]; then SIF_SHA=$(sha256sum "$SIF" | cut -d' ' -f1)
else SIF_SHA=$(cut -d' ' -f1 "$SIF.sha256"); fi
if [[ -n "${RATPAC_SIF_SHA256:-}" && "$SIF_SHA" != "$RATPAC_SIF_SHA256" ]]; then
  echo "ABORT: container sha256 $SIF_SHA != pinned $RATPAC_SIF_SHA256"; exit 4; fi

# ---- simulate --------------------------------------------------------------------------------------------
mkdir -p "$RUN_DIR"; cd "$RUN_DIR"
cp -r "$CODE/ratdb/OBD17kt" .
NAME="${SAMPLE}_s${SEED}"
HEPEVT=""; HEPEVT_SHA=""
if [[ "$MACRO" == alphan_hepevt ]]; then   # pre-sampled final states, fully determined by the chunk seed
  ratx python3 "$CODE/tools/make_alphan_hepevt.py" --seed "$SEED" --n "$NEV" -o "$RUN_DIR/$NAME.alphan"
  HEPEVT="$RUN_DIR/$NAME.alphan.hepevt"; HEPEVT_SHA=$(sha256sum "$HEPEVT" | cut -d' ' -f1)
fi
D=$'\001'   # sed delimiter that cannot occur in a regex or path
VOL_ESC=$(printf '%s' "$VOLUME" | sed -e 's/[\\&]/\\&/g')
sed -e "s${D}__NEVENTS__${D}$NEV${D}g" -e "s${D}__SPECTRUM__${D}$SPEC${D}g" -e "s${D}__SHIELD_MODEL__${D}$SHIELD${D}g" \
    -e "s${D}__LIGHT_YIELD__${D}$LY${D}g" -e "s${D}__LS_MATERIAL__${D}$LS_MATERIAL${D}g" -e "s${D}__ISOTOPE__${D}$ISOTOPE${D}g" \
    -e "s${D}__VOLUME__${D}$VOL_ESC${D}g" -e "s${D}__HEPEVT_FILE__${D}$HEPEVT${D}g" "$CODE/macros/$MACRO.mac" > run.mac
if grep -v '^#' run.mac | grep -q "__[A-Z_]*__"; then echo "ABORT: unfilled placeholder in run.mac"; grep -n "__[A-Z_]*__" run.mac; exit 2; fi
echo "chunk seed=$SEED nev=$NEV macro=$MACRO sample=$SAMPLE spectrum=$SPEC ls=$LS_MATERIAL isotope=$ISOTOPE volume=$VOLUME shield=$SHIELD ly=$LY host=$(hostname) code=$CODE_HASH sif=$SIF_SHA start=$START"
ratx python3 "$CODE/tools/timecmd.py" \
  rat -s "$SEED" -o "$NAME.ntuple.root" -l "$NAME.rat.log" run.mac > "$NAME.out" 2> "$NAME.time" \
  || { echo "rat FAILED"; tail -30 "$NAME.out"; tail -30 "$NAME.rat.log"; exit 1; }
grep -E "Elapsed|User time|Maximum resident" "$NAME.time"

shopt -s nullglob
R=(run*.rndm)   # runN.rndm (run start) + runNevtM.rndm (start of every event)
if (( ${#R[@]} )); then tar --sort=name --mtime=@0 --owner=0 --group=0 -cf "$NAME.rndm_states.tar" "${R[@]}" \
  && rm -f "${R[@]}" currentEvent.rndm currentRun.rndm; fi
echo "rndm states archived: ${#R[@]}"

ratx python3 "$CODE/tools/extract_events.py" "$NAME.ntuple.root" --seed "$SEED" --mode "$MODE" -o "$NAME.events.npz" > "$NAME.summary.json"
cat "$NAME.summary.json"

# ---- provenance ------------------------------------------------------------------------------------------
PYV=$(ratx python3 -c "import sys,numpy,ROOT;print(sys.version.split()[0],numpy.__version__,ROOT.gROOT.GetVersion())" 2>/dev/null || echo "? ? ?")
cat > provenance.json <<EOF
{
 "seed": $SEED, "nevents": $NEV, "spectrum": "$SPEC", "shield_model": "$SHIELD", "light_yield": $LY, "rat_cmd": "rat -s $SEED -o $NAME.ntuple.root -l $NAME.rat.log run.mac",
 "variant": "OBD17kt_geo", "macro": "$MACRO", "sample": "$SAMPLE", "extract_mode": "$MODE", "ls_material": "$LS_MATERIAL",
 "isotope": "$ISOTOPE", "volume_regex": "$(printf '%s' "$VOLUME" | sed 's/\\/\\\\/g; s/"/\\"/g')", "hepevt_sha256": "$HEPEVT_SHA",
 "ibd_geo_table_sha256": "$(sha256sum "$CODE/ratdb/OBD17kt/IBD_GEO.ratdb" 2>/dev/null | cut -d' ' -f1)",
 "container": {"image": "docker://ratpac/ratpac-two:$RATPAC_TAG", "digest": "$RATPAC_DIGEST", "sif_sha256": "$SIF_SHA"},
 "code_manifest_sha256": "$CODE_HASH", "code_snapshot": "$CODE",
 "content_sha256": "$(python3 -c "import json;print(json.load(open('$NAME.summary.json'))['content_sha256'])" 2>/dev/null || grep -o '"content_sha256": "[0-9a-f]*"' "$NAME.summary.json" | cut -d'"' -f4)",
 "python_numpy_root": "$PYV",
 "slurm": {"job_id": "${SLURM_JOB_ID:-}", "array_job_id": "${SLURM_ARRAY_JOB_ID:-}", "array_task_id": "${SLURM_ARRAY_TASK_ID:-}", "partition": "${SLURM_JOB_PARTITION:-}", "restart_count": "${SLURM_RESTART_COUNT:-0}"},
 "host": "$(hostname)", "cpu_model": "$(lscpu | sed -n 's/^Model name:[[:space:]]*//p' | head -1)",
 "cpu_seconds_user": "$(sed -n 's/^User time (seconds): //p' "$NAME.time")",
 "max_rss_kb": "$(sed -n 's/^Maximum resident set size (kbytes): //p' "$NAME.time")",
 "start": "$START", "end": "$(date -Is)"
}
EOF
cp "$CODE/CODE_MANIFEST.sha256" .
sha256sum "$NAME".* run.mac provenance.json CODE_MANIFEST.sha256 > SHA256SUMS   # includes the .alphan.* inputs
echo "CHUNK_OK seed=$SEED end=$(date -Is)"
