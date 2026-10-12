#!/usr/bin/env bash
# Nightly current-season nba_player_impact: build, publish, COMMIT.
#
# Twin of wehoop-wnba-stats-data/scripts/nightly_wnba_impact.sh -- change both
# together. Differences are the season convention (NBA seasons are END years and
# roll over in October; the WNBA plays inside one calendar year) and the store
# path.
#
# WHY THIS COMMITS, when reshape/io.py says released datasets are not committed:
# the impact tables are a MODEL artifact, not one of the reshaped nba_stats_*
# datasets that D36 retired from the tree. A release asset can be overwritten in
# place and carries no history, so the only record of what a given night's model
# produced is the release itself -- committing the table plus its card keeps the
# repo self-describing and gives the model output the git history a published
# decision surface should have. Decision 2026-09-02, recorded in CLAUDE.md and
# models/REGISTRY.md. csv stays release-only (largest format, adds nothing over
# the parquet), matching the twin.
#
# Cron (droplet, ET): 0 4 on the NBA window -- Oct 18-31, Nov-Dec, Jan-Jun and
# the Jul 1-12 tail, mirroring daily_nba_stats.yml. Droplet-viable despite the
# disabled nba-stats SCRAPE cron: this makes ONE live proxied leaguegamelog call
# and then computes offline from the committed store (verified 2026-09-02 at 98%
# CPU, not the socket stall that killed the scrape).
set -uo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR" || exit 1

PY="${HOOPR_NBA_STATS_PYBIN:-}"
if [ -z "${PY}" ]; then
  for cand in .venv/Scripts/python.exe .venv/bin/python; do
    if [ -x "${cand}" ]; then PY="${cand}"; break; fi
  done
fi
[ -n "${PY}" ] || { echo "FATAL: no venv python (uv sync first, or set HOOPR_NBA_STATS_PYBIN)" >&2; exit 1; }

# shellcheck source=scripts/_commit.sh
source "$(dirname "${BASH_SOURCE[0]}")/_commit.sh"
git config --local user.email "action@github.com" >/dev/null 2>&1 || true
git config --local user.name "Github Action" >/dev/null 2>&1 || true

# NBA seasons are END years with an October rollover: October 2025 starts the
# 2025-26 season, keyed 2026. `test -ge` is base-10 even on a zero-padded month
# (unlike $(( )), which would read "08" as octal), so no 10# prefix is needed.
# The season is an OPTIONAL leading 4-digit arg; everything else passes through to
# the CLI. The cron calls `nightly_nba_impact.sh --publish`, which the old
# "$1 is the season" parse turned into SEASON=--publish with no flags forwarded.
if [[ "${1:-}" =~ ^[0-9]{4}$ ]]; then
  SEASON="$1"; shift
else
  YEAR=$(date -u +%Y); MONTH=$(date -u +%m)
  if [ "$MONTH" -ge 10 ]; then SEASON=$((YEAR + 1)); else SEASON=$YEAR; fi
fi
# Lineup source pinned to auto (override: NBA_IMPACT_LINEUP_SOURCE, or pass
# --lineup-source): the published 1997-2026 history was re-run and republished in
# `auto` (rotation-first, quarter_box fallback) on 2026-10-12, so the live season
# must be built the same way as every season before it. `auto` beat quarter_box on
# box-score minutes in all 9 seasons measured, with equal gates and RAPM rank
# correlation >= 0.998 vs the old release (sdv-py #818 measurement, 2026-10-12).
# Changing this again means another full-history re-run in the new mode.
case " $* " in
  *" --lineup-source "*) ;;
  *) set -- "$@" --lineup-source "${NBA_IMPACT_LINEUP_SOURCE:-auto}" ;;
esac
RAW_STORE="${NBA_RAW_STORE:-/mnt/sdv_repos/hoopR-nba-stats-raw/nba_stats/json}"

# A scratch dir, never a repo path: the builder's output is an intermediate, and
# only the parquet + card are meant to survive into the tracked tree below.
OUT_DIR="$(mktemp -d "/tmp/nba_impact_${SEASON}.XXXXXX")"
trap 'rm -rf "${OUT_DIR}"' EXIT

# Publishing is opt-in for this family (see CLAUDE.md): pass --publish through,
# or --dry-run to plan. Extra args are forwarded verbatim.
"$PY" -m nba_model_08_impact \
  --seasons "$SEASON" \
  --out "$OUT_DIR" \
  --raw-store-dir "$RAW_STORE" \
  --repo sportsdataverse/sportsdataverse-data \
  --tag nba_player_impact \
  "$@"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "EXIT=$rc"
  exit "$rc"
fi

# A dry run builds but publishes nothing, so it must not move the tracked tree
# either -- a plan run that silently commits is the same class of surprise as a
# plan run that silently uploads.
case " $* " in
  *" --dry-run "*) echo "dry run: not committing"; echo "EXIT=0"; exit 0 ;;
esac

# Parquet only in the tree (owner rule 2026-09-30); the release carries rds + csv too.
mkdir -p "${REPO_DIR}/nba_stats/player_impact/parquet"
for f in "${OUT_DIR}"/*.parquet; do
  [ -e "$f" ] && cp -f "$f" "${REPO_DIR}/nba_stats/player_impact/parquet/"
done
# The model card is the artifact that says HOW these numbers were produced;
# committing the table without it leaves the repo copy unexplained. It is the
# MERGED card: the CLI overlaid this season onto the release's card (every
# published season + the full-history gates, which a one-season build cannot
# compute) before uploading it -- so the tree and the release hold the same file.
# A --dry-run runs that merge too and prints the would-be card's season span.
for f in "${OUT_DIR}"/*_card.json; do
  [ -e "$f" ] && cp -f "$f" "${REPO_DIR}/nba_stats/player_impact/"
done

sdv_commit_push "NBA Player Impact Update (Start: ${SEASON} End: ${SEASON})" \
  nba_stats/player_impact || rc=1

echo "EXIT=$rc"
exit "$rc"
