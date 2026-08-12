#!/usr/bin/env bash
# Program V (design section 10.4, D26d) operator runbook: the v3 -> production
# release-tag cutover.
#
# Usage: scripts/run_v3_cutover.sh [-s START] [-e END] [-x] [-R] [-L] [-- EXTRA...]
#   -s START  first END-year season (default 1997)
#   -e END    last END-year season  (default 2026)
#   -x        EXECUTE. WITHOUT IT THIS IS A DRY RUN.
#   -R        SEPARATE STEP: retire the _v3 tags (no data upload). With -x, deletes.
#   -L        SEPARATE STEP: retire the LEGACY START-year assets superseded by the
#             publish (no data upload). With -x, deletes. Refuses any season whose
#             END-year replacement is not present and verified in every format.
#   --        everything after is passed through (e.g. --allow-diff 2011:schedule)
#
# The standing, per-game-verified gate allowlist is NOT applied implicitly --
# pass it, so the run always says out loud which diffs it is accepting:
#
#   scripts/run_v3_cutover.sh -- --allow-diff-file ops/v3_cutover_allowlist.txt
#
# Each entry carries its reason and the manifest renders it; an entry without
# one is rendered UNATTRIBUTED rather than quietly accepted.
#
# DRY RUN IS THE DEFAULT. A dry run re-runs the section-10.3 gate, derives the
# release formats, writes the REPLACE MANIFEST to logs/, and uploads nothing.
# Read the manifest's "WOULD BE DESTROYED" and "SEASON-LABEL COLLISION" sections
# before ever passing -x -- overwriting a release asset destroys the previous
# bytes and hoopR::load_nba_*() reads them.
#
# Publishes parquet + rds + csv.gz for every artifact (hoopR reads the .rds; the
# csv is gzipped to stay clear of GitHub's 2 GiB per-asset limit). The rds is
# verified by reading it back before it is ever uploaded.
#
# Decision B: the publish is ADDITIVE -- the END-year assets land next to the
# legacy START-year ones, so an all-NEW / 0-REPLACE manifest is expected. Each
# touched tag gets a generated README.md naming both patterns. Retire the legacy
# names later with -L, never in the same run.
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
RETIRE_LEGACY=""
while getopts "s:e:xRL" opt; do
  case "$opt" in
    s) START="$OPTARG" ;;
    e) END="$OPTARG" ;;
    x) EXECUTE="--execute" ;;
    R) RETIRE="--retire-v3-tags" ;;
    L) RETIRE_LEGACY="--retire-legacy-assets" ;;
    *) echo "usage: $0 [-s START] [-e END] [-x] [-R] [-L] [-- EXTRA...]" >&2; exit 2 ;;
  esac
done
shift $((OPTIND - 1))

# The two retirements are separate steps by design; refuse to conflate them here
# rather than relying on the module to catch it after the log header lies.
if [ -n "$RETIRE" ] && [ -n "$RETIRE_LEGACY" ]; then
  echo "-R and -L are separate steps; run one at a time." >&2
  exit 2
fi

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
echo "v3 cutover seasons $START-$END ${RETIRE:+(tag retirement only)}${RETIRE_LEGACY:+(legacy-asset retirement only)}"
echo "watch live: tail -f $REPO_ROOT/$LOG"

# Direct venv python, NOT `uv run` (avoids a surprise re-lock/resync mid-publish).
"$REPO_ROOT/python/.venv/Scripts/python.exe" -m nba_data_build.v3_cutover \
  -s "$START" -e "$END" $EXECUTE $RETIRE $RETIRE_LEGACY "$@" >> "$LOG" 2>&1
rc=$?
echo "EXIT=$rc" | tee -a "$LOG"
echo "manifest: $(grep -o 'MANIFEST: .*' "$LOG" | tail -1 | cut -d' ' -f2-)"
exit $rc
