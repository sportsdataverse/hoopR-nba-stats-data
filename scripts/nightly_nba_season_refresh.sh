#!/usr/bin/env bash
# Nightly current-season refresh of the release assets the daily compile
# (daily_nba_stats.yml) does NOT build:
#
#   1. Program V v3 families -> nba_stats_{schedules,pbp,possessions,game_lineups}
#      (the nba_*_{season}.* assets -- the ones sdv-py's load_nba_stats_* read)
#   2. the league-dash cube  -> nba_stats_leaguedash
#   3. raw-store compiles    -> nba_stats_{synergy,matchups,hustle,draft_combine}
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
RAWC_OUT="$(mktemp -d "/tmp/nba_rawc_${SEASON}.XXXXXX")"
trap 'rm -rf "${CACHE_DIR}" "${RAWC_OUT}"' EXIT

echo "=== nightly season refresh ${SEASON} started $(date -u +'%F %T')Z ==="
git pull -q --ff-only || echo "WARN: git pull failed -- continuing on the checked-out tree"

# Commit + push helper, shared with the processor and the impact driver.
# shellcheck source=scripts/_commit.sh
source "$(dirname "${BASH_SOURCE[0]}")/_commit.sh"
git config --local user.email "action@github.com" >/dev/null 2>&1 || true
git config --local user.name "Github Action" >/dev/null 2>&1 || true
# Tree dir (release tag minus nba_stats_) per staged v3 family; staged names
# already equal the release asset names (nba_{family}_{season}.parquet).
declare -A V3_KEY=([schedule]=schedules [play_by_play]=pbp [possessions]=possessions [lineups]=game_lineups)
TREE_PATHS=()
# Copy one built parquet into the tree dir -- never in a dry run, which publishes
# nothing and so must not move the tracked tree either.
tree_copy() {
  [ -n "${EXECUTE}" ] && [ -s "$1" ] || return 0
  mkdir -p "$2" && cp -f "$1" "$2/" && TREE_PATHS+=("$2")
}

rc=0
captured=$(find "${RAW_ROOT}/nba_stats/json/playbyplayv3/${SEASON}" -name '*.json' 2>/dev/null | wc -l)
if [ "${captured}" -eq 0 ]; then
  echo "v3: no playbyplayv3 captured for ${SEASON} under ${RAW_ROOT} -- nothing to publish (not an error)"
elif "$PY" -m nba_data_build.v3_backfill -s "$SEASON" -e "$SEASON" \
       --raw-root "$RAW_ROOT" --cache-dir "$CACHE_DIR" --rebuild; then
  # --no-readme: each tag's README states the full published season range; a
  # one-season run would rewrite it as "${SEASON}-${SEASON}".
  if "$PY" -m nba_data_build.v3_cutover -s "$SEASON" -e "$SEASON" \
       --raw-root "$RAW_ROOT" --no-readme \
       --manifest "${REPO_DIR}/build_out/v3_cutover_manifest_nightly.md" \
       ${EXECUTE}; then
    # Owner rule: the tree carries every compiled dataset's parquet (release
    # carries all three formats). Only after a publish, so the tree never shows
    # a season the release does not.
    for fam in "${!V3_KEY[@]}"; do
      tree_copy "v3_staging/nba_${fam}_${SEASON}.parquet" "nba_stats/${V3_KEY[$fam]}/parquet"
    done
  else
    rc=1
  fi
else
  rc=1
fi

# Persistent out dir, not scratch: the megas assemble from on-disk tables, so a
# variant that fails today keeps yesterday's file instead of narrowing the mega.
if "$PY" -m nba_data_build.leaguedash_cli --seasons "$SEASON" \
     --out build_out/leaguedash "${LD_MODE}"; then
  for src in build_out/leaguedash/nba_stats_leaguedash/*_"${SEASON}".parquet; do
    tree_copy "$src" nba_stats/leaguedash/parquet
  done
else
  rc=1
fi

# Raw-store compiles (no network): hoopR-nba-stats-raw's 08:00 daily re-fetches
# these season-level payloads for the current season, but nothing compiled them
# on a schedule -- the tags sat at the 2026-09-30 operator publish. Each CLI skips
# a season with no rows (synergy/hustle/matchups are empty until games are
# played), so this no-ops before tip-off. The combine year is the same END key
# (2027 = the 2026 combine, the file the raw daily refreshes). May-Jul the
# raw daily also looks one key ahead for the combine (the May combine belongs to
# NEXT season's key), so compile that key too. PIPELINE_MONTH overrides for tests.
CMONTH=$((10#${PIPELINE_MONTH:-$(date -u +%m)}))
COMBINE_YEARS="$SEASON"
if [ "$CMONTH" -ge 5 ] && [ "$CMONTH" -le 7 ]; then COMBINE_YEARS="$SEASON $((SEASON + 1))"; fi
for spec in synergy_cli:--seasons:synergy matchups_cli:--seasons:matchups \
            hustle_cli:--seasons:hustle combine_cli:--years:draft_combine; do
  IFS=: read -r cli flag key <<< "${spec}"
  years="$SEASON"; [ "$key" = draft_combine ] && years="$COMBINE_YEARS"
  # shellcheck disable=SC2086  # $years is a space-separated year list
  if "$PY" -m "nba_data_build.${cli}" "${flag}" $years \
       --raw-root "${RAW_ROOT}/nba_stats/json" --out "${RAWC_OUT}" "${LD_MODE}"; then
    for y in $years; do
      for src in "${RAWC_OUT}/nba_stats_${key}"/*_"${y}".parquet; do
        [ -e "$src" ] && tree_copy "$src" "nba_stats/${key}/parquet"
      done
    done
  else
    rc=1
  fi
done

if [ "${#TREE_PATHS[@]}" -gt 0 ]; then
  # END year, matching this repo's history; (Start: YYYY End: YYYY) is parsed downstream.
  sdv_commit_push "NBA Stats Update (Start: ${SEASON} End: ${SEASON})" \
    $(printf '%s\n' "${TREE_PATHS[@]}" | sort -u) || rc=1
fi

echo "=== nightly season refresh ${SEASON} finished $(date -u +'%F %T')Z ==="
echo "EXIT=${rc}"
exit "${rc}"
