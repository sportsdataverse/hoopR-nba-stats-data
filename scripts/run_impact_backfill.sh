#!/usr/bin/env bash
# User-executable launcher for the NBA player-impact backfill (P0 droplet host).
#
# Usage:
#   bash scripts/run_impact_backfill.sh [SEASONS] [extra nba_model_publish args...]
#     SEASONS   'YYYY:YYYY' or 'YYYY', season END-years e.g. 2024 = 2023-24
#               (default 1997:2026)
#     extras    forwarded verbatim to `nba_model_publish impact`
#
# PUBLISHING IS OPT-IN -- pass --publish or this builds only:
#   ... run_impact_backfill.sh 2025 --publish   # builds AND uploads to the tag
#   ... run_impact_backfill.sh 2025             # builds only, release untouched
#   ... run_impact_backfill.sh 2025 --dry-run   # builds, prints the upload plan
# A run without --publish still exits 0; `publish: skipped` in the log is the
# tell. The daily droplet cron passes --publish (scripts/P0_DROPLET_RUNBOOK.md).
#
# Watch live (exact path printed at start):
#   tail -f logs/impact_backfill_<timestamp>.log
#
# Inputs: a history rebuild MUST read the committed raw store (SDV_PY_NBA_RAW_JSON_DIR, default the sibling
# hoopR-nba-stats-raw checkout) and a FULL possession cache (SDV_PY_NBA_CACHE_DIR). The script warns on both.
#
# Resume: the per-game parquet cache ($SDV_PY_NBA_CACHE_DIR) is the checkpoint.
# Ctrl-C anytime and rerun the same command -- already-compiled games are
# skipped, only live fetches sleep.
#
# Tuning / egress -- env only, no code changes:
#   SDV_NBA_DELAY_S       sleep between live per-game fetches (default 0.6;
#                         use ~7 for an unattended multi-season backfill --
#                         the ~250 req/10min stats.nba.com budget is SHARED
#                         with the R daily scraper)
#   SDV_PY_NBA_CACHE_DIR  possession cache dir (default /data/nba_possessions)
#   PROXY_ENDPOINT/_KEY/_PKG  ProxyBonanza pool (the default egress)
#   NO_PROXY_DIRECT=1     pass --no-proxy: fetch from this host's own IP
#                         (residential only), or through https_proxy/http_proxy
#                         if exported (the Decodo fallback -- libcurl honors them)
set -u  # deliberately not -e: the EXIT= marker must be written on failure too
cd "$(dirname "$0")/.." || exit 1

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
: "${SDV_PY_NBA_CACHE_DIR:=/data/nba_possessions}"
export SDV_PY_NBA_CACHE_DIR

# A history rebuild reads the box logs from the committed raw store. Without it, leaguegamelog is fetched
# live, and live minutes have drifted from the captures the release was built from. On 2026-11-26 that put
# bpm up to 49 off in the 1997-2000 playoffs. The store-backed fetch still goes live on a miss, for example a
# current-season day the store has not captured yet. Point SDV_PY_NBA_RAW_JSON_DIR elsewhere to override it.
: "${SDV_PY_NBA_RAW_JSON_DIR:=$PWD/../hoopR-nba-stats-raw/nba_stats/json}"
if [ -d "$SDV_PY_NBA_RAW_JSON_DIR" ]; then
  export SDV_PY_NBA_RAW_JSON_DIR
else
  echo "WARNING: raw store $SDV_PY_NBA_RAW_JSON_DIR not found: box logs will be fetched LIVE" >&2
  unset SDV_PY_NBA_RAW_JSON_DIR
fi
# The possession cache must hold every game of the seasons built (about 38,000 for 1997-2026). Otherwise the
# build compiles the missing games live, slowly, through the proxy pool.
N_CACHED=$(find "$SDV_PY_NBA_CACHE_DIR/possessions" -maxdepth 1 -name '*.parquet' 2>/dev/null | wc -l)
if [ "$N_CACHED" -lt 1000 ]; then
  echo "WARNING: possession cache $SDV_PY_NBA_CACHE_DIR holds $N_CACHED games: point SDV_PY_NBA_CACHE_DIR at a full cache" >&2
fi

SEASONS="${1:-1997:2026}"
[ $# -gt 0 ] && shift

mkdir -p logs "$SDV_PY_NBA_CACHE_DIR"
LOG="logs/impact_backfill_$(date +%Y%m%d_%H%M%S).log"

# timestamp every line so a hang shows up as a stalled clock, not a mystery
stamp() { while IFS= read -r line; do printf '[%s] %s\n' "$(date -u '+%F %T')" "$line"; done; }

EXTRA=()
if [ "${NO_PROXY_DIRECT:-0}" = "1" ]; then EXTRA+=(--no-proxy); fi

echo "log:   $PWD/$LOG"
echo "watch: tail -f $PWD/$LOG"
printf 'impact backfill seasons=%s cache=%s (%s games) raw_store=%s delay_s=%s no_proxy_direct=%s\n' \
  "$SEASONS" "$SDV_PY_NBA_CACHE_DIR" "$N_CACHED" "${SDV_PY_NBA_RAW_JSON_DIR:-LIVE}" "${SDV_NBA_DELAY_S:-0.6(default)}" \
  "${NO_PROXY_DIRECT:-0}" | stamp | tee -a "$LOG"

( uv run python -m nba_model_publish impact \
    --seasons "$SEASONS" \
    --out build_out/impact \
    ${EXTRA[@]+"${EXTRA[@]}"} \
    "$@" ) 2>&1 | stamp | tee -a "$LOG"
rc=${PIPESTATUS[0]}
echo "EXIT=$rc" | stamp | tee -a "$LOG"
exit "$rc"
