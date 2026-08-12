#!/usr/bin/env bash
# Program V (design section 9.4) operator runbook: v3 backfill from the raw store.
#
# Usage: scripts/run_v3_backfill.sh [-s START] [-e END] [-r]
#   -s START  first END-year season (default 1997)
#   -e END    last END-year season  (default 2026)
#   -r        rebuild seasons whose staged parquets already exist
#
# Resumable: per-game cache + per-season checkpoint (a season with all four
# staged parquets is skipped). Ctrl-C is safe; rerun to continue.
# Writes ONLY to the gitignored v3_staging/ dir -- run v3_gate before any cutover.
set -u
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

START=1997
END=2026
REBUILD=""
while getopts "s:e:r" opt; do
  case "$opt" in
    s) START="$OPTARG" ;;
    e) END="$OPTARG" ;;
    r) REBUILD="--rebuild" ;;
    *) echo "usage: $0 [-s START] [-e END] [-r]" >&2; exit 2 ;;
  esac
done

mkdir -p logs
LOG="logs/v3_backfill_$(date -u +%Y%m%dT%H%M%SZ).log"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
export PYTHONPATH="$REPO_ROOT/python"

echo "v3 backfill seasons $START-$END -> $REPO_ROOT/v3_staging"
echo "watch live: tail -f $REPO_ROOT/$LOG"

# Direct venv python, NOT `uv run` (avoids a surprise re-lock/resync mid-backfill).
"$REPO_ROOT/python/.venv/Scripts/python.exe" -m nba_data_build.v3_backfill \
  -s "$START" -e "$END" $REBUILD >> "$LOG" 2>&1
rc=$?
echo "EXIT=$rc" | tee -a "$LOG"
echo "next: PYTHONPATH=python python/.venv/Scripts/python.exe -m nba_data_build.v3_gate -s $START -e $END"
exit $rc
