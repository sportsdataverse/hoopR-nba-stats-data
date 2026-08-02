#!/usr/bin/env bash
# User-executable launcher for the NBA player-impact backfill (P0 droplet host).
#
# Usage:
#   bash scripts/run_impact_backfill.sh [SEASONS] [extra nba_model_publish args...]
#     SEASONS   'YYYY:YYYY' or 'YYYY', season END-years e.g. 2024 = 2023-24
#               (default 1997:2026)
#     extras    forwarded verbatim, e.g. --dry-run for a no-upload smoke run
#
# Watch live (exact path printed at start):
#   tail -f logs/impact_backfill_<timestamp>.log
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
printf 'impact backfill seasons=%s cache=%s delay_s=%s no_proxy_direct=%s\n' \
  "$SEASONS" "$SDV_PY_NBA_CACHE_DIR" "${SDV_NBA_DELAY_S:-0.6(default)}" \
  "${NO_PROXY_DIRECT:-0}" | stamp | tee -a "$LOG"

( uv run python -m nba_model_publish impact \
    --seasons "$SEASONS" \
    --out build_out/impact \
    ${EXTRA[@]+"${EXTRA[@]}"} \
    "$@" ) 2>&1 | stamp | tee -a "$LOG"
rc=${PIPESTATUS[0]}
echo "EXIT=$rc" | stamp | tee -a "$LOG"
exit "$rc"
