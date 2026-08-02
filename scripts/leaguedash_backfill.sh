#!/usr/bin/env bash
# Full-history backfill for stats.nba.com league-dash data (NBA only --
# WNBA backfill lives in wehoop-wnba-stats-data/python/leaguedash_backfill.sh
# since WNBA leaguedash moved to its own producer repo).
# Run this DIRECTLY in your own terminal from a residential IP -- NOT via Claude,
# NOT in the background. It is a multi-hour, rate-limited job.
#
# Season floor below (1996) is a domain-knowledge estimate, NOT verified
# against a live stats.nba.com response in this session -- the scraper's own
# per-variant try/except + empty-frame skip absorbs a wrong guess for free
# (a pre-history season just logs "leaguedash_empty"/"skip" and costs a
# little rate-limit budget). Narrow --start/--end below if you'd rather not
# spend that budget probing the edges. 2024/2025 are already seeded --
# START defaults to 1996 and stops at 2023 so this never re-scrapes them.
#
# Resumable: safe to Ctrl-C and re-run. Each season is a separate `uv run`
# invocation; completion is tracked via a ".done_<season>" sentinel (NOT
# player_master_<season>.parquet -- some seasons genuinely have no data
# beyond standings, e.g. 1996, so that file never gets written and a
# marker keyed on it would re-attempt that season forever). The sentinel
# is only written when the CLI exits 0 -- leaguedash_cli.py now returns 1
# if any file failed to publish, so a real publish failure correctly
# leaves the season unmarked and it retries on the next run instead of
# silently reporting done. --publish runs after EVERY season, so progress
# is banked upstream incrementally, not just sitting on local disk for hours.
set -uo pipefail   # no -e: one bad season must not kill the whole backfill

REPO_DIR="/c/Users/saiem/Documents/GitHub-Data/sdv-dev/hoopR-dev/hoopR-nba-stats-data/python"
OUT_DIR="build_out/leaguedash"          # same dir the seed 2024/2025 run used
TAG="nba_stats_leaguedash"
LOG="$REPO_DIR/leaguedash_backfill.log"
START="${1:-1996}"
END="${2:-2023}"

cd "$REPO_DIR" || exit 1

if [ -z "${PROXY_ENDPOINT:-}" ] || [ -z "${PROXY_KEY:-}" ] || [ -z "${PROXY_PKG:-}" ]; then
  echo "PROXY_ENDPOINT / PROXY_KEY / PROXY_PKG are not set as OS env vars." >&2
  echo "Python cannot read .Renviron -- export them in THIS shell first, e.g.:" >&2
  echo "  export PROXY_ENDPOINT=... PROXY_KEY=... PROXY_PKG=..." >&2
  echo "Without them, calls fall through to direct (unproxied) and will 429 fast." >&2
  exit 1
fi
gh auth status >/dev/null 2>&1 || { echo "gh is not authenticated -- --publish will fail." >&2; exit 1; }

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
# Tunable without editing this script (defaults: 3 hits / 250 calls / 600s window):
#   export STATS_RATE_HITS=3 STATS_RATE_MAX=250 STATS_RATE_WINDOW=600

for season in $(seq "$START" "$END"); do
  marker="$OUT_DIR/$TAG/.done_${season}"
  if [ -f "$marker" ]; then
    echo "$(date -Iseconds) SKIP season=$season (already built)" | tee -a "$LOG"
    continue
  fi
  echo "$(date -Iseconds) START season=$season" | tee -a "$LOG"
  uv run python -m nba_data_build.leaguedash_cli \
    --seasons "$season" --out "$OUT_DIR" --publish >> "$LOG" 2>&1
  rc=$?
  echo "$(date -Iseconds) EXIT=$rc season=$season" | tee -a "$LOG"
  if [ "$rc" -eq 0 ]; then
    touch "$marker"
  else
    echo "$(date -Iseconds) WARNING season=$season did not exit cleanly -- will retry on next run" | tee -a "$LOG"
  fi
  sleep 5   # small gap so a fresh per-process rate-limit window doesn't stack on the tail of the last
done

echo "$(date -Iseconds) BACKFILL DONE" | tee -a "$LOG"
