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
# Cron (droplet, ET): the NBA window, after the raw store is refreshed.
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
if [ -n "${1:-}" ]; then
  SEASON="$1"
else
  YEAR=$(date -u +%Y); MONTH=$(date -u +%m)
  if [ "$MONTH" -ge 10 ]; then SEASON=$((YEAR + 1)); else SEASON=$YEAR; fi
fi
RAW_STORE="${NBA_RAW_STORE:-/mnt/sdv_repos/hoopR-nba-stats-raw/nba_stats/json}"

# A scratch dir, never a repo path: the builder's output is an intermediate, and
# only the parquet/rds/card are meant to survive into the tracked tree below.
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
  "${@:2}"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "EXIT=$rc"
  exit "$rc"
fi

# A dry run builds but publishes nothing, so it must not move the tracked tree
# either -- a plan run that silently commits is the same class of surprise as a
# plan run that silently uploads.
case " ${*:2} " in
  *" --dry-run "*) echo "dry run: not committing"; echo "EXIT=0"; exit 0 ;;
esac

mkdir -p "${REPO_DIR}/nba_stats/player_impact/parquet" \
         "${REPO_DIR}/nba_stats/player_impact/rds"
for f in "${OUT_DIR}"/*.parquet; do
  [ -e "$f" ] && cp -f "$f" "${REPO_DIR}/nba_stats/player_impact/parquet/"
done
for f in "${OUT_DIR}"/*.rds; do
  [ -e "$f" ] && cp -f "$f" "${REPO_DIR}/nba_stats/player_impact/rds/"
done
# The model card is the artifact that says HOW these numbers were produced;
# committing the table without it leaves the repo copy unexplained.
for f in "${OUT_DIR}"/*_card.json; do
  [ -e "$f" ] && cp -f "$f" "${REPO_DIR}/nba_stats/player_impact/"
done

sdv_commit_push "NBA Player Impact Update (Start: ${SEASON} End: ${SEASON})" \
  nba_stats/player_impact || rc=1

echo "EXIT=$rc"
exit "$rc"
