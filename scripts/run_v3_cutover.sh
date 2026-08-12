#!/usr/bin/env bash
# Program V (design section 10.4, D26d) operator runbook: the v3 -> production
# release-tag cutover.
#
# Usage: scripts/run_v3_cutover.sh [-s START] [-e END] [-x] [-R] [-- EXTRA...]
#   -s START  first END-year season (default 1997)
#   -e END    last END-year season  (default 2026)
#   -x        EXECUTE the publish. WITHOUT IT THIS IS A DRY RUN.
#   -R        SEPARATE STEP: retire the _v3 tags (no data upload). With -x, deletes.
#   --        everything after is passed through (e.g. --allow-diff 2011:schedule)
#
# DRY RUN IS THE DEFAULT. A dry run re-runs the section-10.3 gate, writes the
# REPLACE MANIFEST to logs/, and uploads nothing. Read the manifest's
# "WOULD BE DESTROYED" section before ever passing -x -- overwriting a release
# asset destroys the previous bytes and hoopR::load_nba_*() reads them.
#
# Resumable + idempotent: verified uploads are recorded in
# v3_staging/.cutover_receipts.json and skipped on a re-run. On the first
# size mismatch the run stops rather than continuing through the queue.
set -u
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

START=1997
END=2026
EXECUTE=""
RETIRE=""
while getopts "s:e:xR" opt; do
  case "$opt" in
    s) START="$OPTARG" ;;
    e) END="$OPTARG" ;;
    x) EXECUTE="--execute" ;;
    R) RETIRE="--retire-v3-tags" ;;
    *) echo "usage: $0 [-s START] [-e END] [-x] [-R] [-- EXTRA...]" >&2; exit 2 ;;
  esac
done
shift $((OPTIND - 1))

mkdir -p logs
LOG="logs/v3_cutover_$(date -u +%Y%m%dT%H%M%SZ).log"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
export PYTHONPATH="$REPO_ROOT/python"

if [ -n "$EXECUTE" ]; then
  echo "*** EXECUTE MODE -- this WILL overwrite release assets on sportsdataverse-data ***"
else
  echo "dry run (default) -- nothing will be uploaded; pass -x to publish"
fi
echo "v3 cutover seasons $START-$END ${RETIRE:+(tag retirement only)}"
echo "watch live: tail -f $REPO_ROOT/$LOG"

# Direct venv python, NOT `uv run` (avoids a surprise re-lock/resync mid-publish).
"$REPO_ROOT/python/.venv/Scripts/python.exe" -m nba_data_build.v3_cutover \
  -s "$START" -e "$END" $EXECUTE $RETIRE "$@" >> "$LOG" 2>&1
rc=$?
echo "EXIT=$rc" | tee -a "$LOG"
echo "manifest: $(grep -o 'MANIFEST: .*' "$LOG" | tail -1 | cut -d' ' -f2-)"
exit $rc
