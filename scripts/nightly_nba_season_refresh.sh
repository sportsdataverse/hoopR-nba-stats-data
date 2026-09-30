#!/usr/bin/env bash
# Nightly current-season refresh of the release assets the daily compile
# (daily_nba_stats.yml) does NOT build:
#
#   1. Program V v3 families -> nba_stats_{schedules,pbp,possessions,game_lineups}
#      (the nba_*_{season}.* assets -- the ones sdv-py's load_nba_stats_* read)
#   2. the league-dash cube  -> nba_stats_leaguedash
#
# Both were operator-only runs: 2025-26 was published once after the Finals
# (2026-08-13), and nothing would have created a single 2026-27 v3 asset. Twin of
# wehoop-wnba-stats-data/scripts/nightly_wnba_season_refresh.sh, where the same
# gap left the 2026 WNBA assets frozen for seven weeks mid-season.
#
# Droplet cron, not CI: leaguedash scrapes stats.nba.com live (403s/hangs from
# datacenter IPs without the PROXY_* pool -- through it, measured 2026-08-13),
# and the v3 build reads the sibling raw checkout.
#
# The v3 half is a clean no-op until hoopR-nba-stats-raw has captured a game for
# the season -- its daily scrape cron has been DISABLED on the droplet since
# 2026-08-11. The gate diffs against a committed legacy
# nba_stats/schedules/parquet/schedule_{span}.parquet only where one exists; the
# Python compile only restamps existing ones and there is none for 2026-27, so the
# current season validates against the raw store and, unlike the WNBA twin, has no
# ordering dependency on the compile. (2025-26 does have one -- a pre-Finals R-era
# snapshot listing the unplayed games 6-7 -- so re-running that season fails the
# gate by design; the Aug 13 publish allowlisted it.)
#
# Cron (droplet, ET): 15 10 18-31 10 * / 15 10 * 1-6,11,12 *
#
#   bash scripts/nightly_nba_season_refresh.sh            # current season
#   bash scripts/nightly_nba_season_refresh.sh 2027 -n    # build + gate + plan, upload nothing
set -uo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR" || exit 1

PY="${HOOPR_NBA_STATS_PYBIN:-}"
if [ -z "${PY}" ]; then
  for cand in .venv/bin/python .venv/Scripts/python.exe; do
    if [ -x "${cand}" ]; then PY="${cand}"; break; fi
  done
fi
[ -n "${PY}" ] || { echo "FATAL: no venv python (uv sync first, or set HOOPR_NBA_STATS_PYBIN)" >&2; echo "EXIT=1"; exit 1; }

# Proxy credentials live in ~/.Renviron, which only R loads -- lift them here
# (same block as scripts/nightly_nba_impact.sh). Never echoed.
for f in "${HOME}/.Renviron" "${HOME}/Documents/.Renviron"; do
  [ -f "${f}" ] || continue
  for v in PROXY_ENDPOINT PROXY_KEY PROXY_PKG; do
    if [ -z "${!v:-}" ]; then
      val="$(sed -nE "s/^[[:space:]]*${v}[[:space:]]*=[[:space:]]*//p" "${f}" \
             | head -1 | tr -d "\"'" | tr -d '\r')"
      [ -n "${val}" ] && export "${v}=${val}"
    fi
  done
done

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
export PYTHONPATH="${REPO_DIR}/python${PYTHONPATH:+:${PYTHONPATH}}"

# NBA seasons are END years with an October rollover (October 2026 opens 2026-27,
# keyed 2027). `-ge` is base-10 even on a zero-padded month.
if [ -n "${1:-}" ]; then
  SEASON="$1"
else
  YEAR=$(date -u +%Y); MONTH=$(date -u +%m)
  if [ "$MONTH" -ge 10 ]; then SEASON=$((YEAR + 1)); else SEASON=$YEAR; fi
fi
EXECUTE="--execute"; LD_MODE="--publish"
if [ "${2:-}" = "-n" ]; then EXECUTE=""; LD_MODE="--dry-run"; fi
RAW_ROOT="${NBA_RAW_CHECKOUT:-/mnt/sdv_repos/hoopR-nba-stats-raw}"
# A fresh per-game cache every run: it is keyed by game id only, so a sdv-py
# bump would otherwise keep serving frames the old engine built.
CACHE_DIR="$(mktemp -d "/tmp/nba_v3_cache_${SEASON}.XXXXXX")"
trap 'rm -rf "${CACHE_DIR}"' EXIT

echo "=== nightly season refresh ${SEASON} started $(date -u +'%F %T')Z ==="
git pull -q --ff-only || echo "WARN: git pull failed -- continuing on the checked-out tree"

rc=0
captured=$(find "${RAW_ROOT}/nba_stats/json/playbyplayv3/${SEASON}" -name '*.json' 2>/dev/null | wc -l)
if [ "${captured}" -eq 0 ]; then
  echo "v3: no playbyplayv3 captured for ${SEASON} under ${RAW_ROOT} -- nothing to publish (not an error)"
elif "$PY" -m nba_data_build.v3_backfill -s "$SEASON" -e "$SEASON" \
       --raw-root "$RAW_ROOT" --cache-dir "$CACHE_DIR" --rebuild; then
  # --no-readme: each tag's README states the full published season range; a
  # one-season run would rewrite it as "${SEASON}-${SEASON}".
  "$PY" -m nba_data_build.v3_cutover -s "$SEASON" -e "$SEASON" \
    --raw-root "$RAW_ROOT" --no-readme \
    --manifest "${REPO_DIR}/build_out/v3_cutover_manifest_nightly.md" \
    ${EXECUTE} || rc=1
else
  rc=1
fi

# Persistent out dir, not scratch: the megas assemble from on-disk tables, so a
# variant that fails today keeps yesterday's file instead of narrowing the mega.
"$PY" -m nba_data_build.leaguedash_cli --seasons "$SEASON" \
  --out build_out/leaguedash "${LD_MODE}" || rc=1

echo "=== nightly season refresh ${SEASON} finished $(date -u +'%F %T')Z ==="
echo "EXIT=${rc}"
exit "${rc}"
