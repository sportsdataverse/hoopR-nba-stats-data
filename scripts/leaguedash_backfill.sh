#!/usr/bin/env bash
# Backfill the stats.nba.com league-dash cube (NBA only -- the WNBA backfill
# lives in wehoop-wnba-stats-data/scripts/leaguedash_backfill.sh, mirroring the
# hoopR/wehoop producer split. The two scripts are deliberate twins; keep them
# in step.)
#
# THIS SCRIPT CANNOT PUBLISH. It builds; the release step lives elsewhere.
# It used to pass --publish unconditionally and upload after every season,
# which put a live release one stray invocation away from a rewrite -- the same
# hazard as the R creation stages that overwrote three WNBA 2025 tags. An
# opt-in flag was the first fix and was still wrong: a flag can be typed by
# accident or copied out of a runbook line, whereas a script with no upload
# path cannot publish at all. To publish, run the module directly and mean it:
#
#   python -m nba_data_build.leaguedash_cli --seasons 2026 --publish
#
#   bash scripts/leaguedash_backfill.sh                 # build 1996-2023
#   bash scripts/leaguedash_backfill.sh -s 2026 -e 2026 # build one season
#   bash scripts/leaguedash_backfill.sh -s 2026 -e 2026 -n   # plan uploads, upload nothing
#
# Run this DIRECTLY in your own terminal from a residential IP for a long range:
# stats.nba.com is rate-limited and IP-sensitive, and a full-history sweep is a
# multi-hour job. A single season is a few minutes and is fine to background.
#
# Season floor 1996 is a domain estimate, not a probe result; the scraper's
# per-variant try/except + empty-frame skip absorbs a wrong guess for the price
# of a little rate budget. END defaults to 2023 because 2024/2025 were seeded by
# an earlier run.
#
# Resumable: safe to Ctrl-C and re-run. Completion is tracked per season with a
# sentinel keyed to the MODE, so a build-only pass is never mistaken for a
# published one. The sentinel is written only on a clean exit -- a failure
# leaves the season unmarked so it retries rather than silently reporting done.
# Sentinels are NOT keyed on player_master_<season>.parquet: some early seasons
# (1996) genuinely have no data beyond standings, so that file never appears and
# a marker keyed on it would re-attempt those seasons forever.
set -uo pipefail   # no -e: one bad season must not kill the whole backfill

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG="nba_stats_leaguedash"

START=1996
END=2023
PUBLISH=""
MODE="build"
OUT_DIR="${REPO_DIR}/build_out/leaguedash"

while getopts s:e:o:n flag; do
    case "${flag}" in
        s) START="${OPTARG}" ;;
        e) END="${OPTARG}" ;;
        o) OUT_DIR="${OPTARG}" ;;
        n) PUBLISH="--dry-run"; MODE="dryrun" ;;
        *) echo "usage: $0 [-s start] [-e end] [-o out] [-n dry-run]" >&2; exit 2 ;;
    esac
done

# Validate the range before anything else: a non-numeric or inverted range makes
# `seq` emit nothing, so the loop body never runs and the script closes with
# "BACKFILL DONE" + EXIT=0 having built nothing -- the reports-success-while-
# doing-nothing failure this repo keeps hitting.
for v in "${START}" "${END}"; do
    case "${v}" in
        ''|*[!0-9]*)
            echo "::error ::-s/-e must be numeric seasons (got -s '${START}' -e '${END}')" >&2
            exit 2
            ;;
    esac
done
if [ "${START}" -gt "${END}" ]; then
    echo "::error ::-s ${START} is after -e ${END}; that range builds nothing" >&2
    exit 2
fi

LOG="${REPO_DIR}/logs/leaguedash_backfill.log"
mkdir -p "$(dirname "${LOG}")" "${OUT_DIR}"

# Venv interpreter by absolute path, not `uv run`: matches
# daily_nba_stats_python_processor.sh, and keeps an orchestrator-launched run
# from re-locking uv.lock as a side effect.
# An explicit override is honoured strictly: falling back from a bad override
# would run a different interpreter than the one asked for.
if [ -n "${HOOPR_NBA_STATS_PYBIN:-}" ]; then
    PYBIN="${HOOPR_NBA_STATS_PYBIN}"
    if [ ! -x "${PYBIN}" ]; then
        echo "::error ::HOOPR_NBA_STATS_PYBIN=${PYBIN} is not executable" >&2
        exit 1
    fi
elif [ -x "${REPO_DIR}/.venv/bin/python" ]; then          # unix layout
    PYBIN="${REPO_DIR}/.venv/bin/python"
elif [ -x "${REPO_DIR}/.venv/Scripts/python.exe" ]; then  # windows layout
    PYBIN="${REPO_DIR}/.venv/Scripts/python.exe"
else
    echo "::error ::no venv interpreter under ${REPO_DIR}/.venv -- run 'uv sync'" >&2
    exit 1
fi

# Proxy credentials: python cannot read ~/.Renviron, so lift them here at call
# time. Values are never echoed and never written to the log.
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
if [ -z "${PROXY_ENDPOINT:-}" ] || [ -z "${PROXY_KEY:-}" ] || [ -z "${PROXY_PKG:-}" ]; then
    echo "PROXY_ENDPOINT / PROXY_KEY / PROXY_PKG are not set and were not found in .Renviron." >&2
    echo "Export them in THIS shell, or add them to ~/.Renviron." >&2
    echo "Without them, calls fall through to direct (unproxied) and will 429 fast." >&2
    exit 1
fi
# No gh-auth check: this script never uploads, so gh is not on its path.

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
export PYTHONPATH="${REPO_DIR}/python${PYTHONPATH:+:${PYTHONPATH}}"
# Rate limits are env-tunable so pace changes need no edit here:
#   export STATS_RATE_HITS=3 STATS_RATE_MAX=250 STATS_RATE_WINDOW=600

echo "$(date -Iseconds) BACKFILL START seasons=${START}-${END} mode=${MODE} out=${OUT_DIR}" | tee -a "${LOG}"
echo "$(date -Iseconds) nothing is uploaded by this script; publish with 'python -m nba_data_build.leaguedash_cli --seasons <y> --publish'" | tee -a "${LOG}"

overall_rc=0
failed=()

for season in $(seq "${START}" "${END}"); do
    marker="${OUT_DIR}/${TAG}/.done_${MODE}_${season}"
    if [ -f "${marker}" ]; then
        echo "$(date -Iseconds) SKIP season=${season} (already ${MODE})" | tee -a "${LOG}"
        continue
    fi
    echo "$(date -Iseconds) START season=${season}" | tee -a "${LOG}"
    "${PYBIN}" -m nba_data_build.leaguedash_cli \
        --seasons "${season}" --out "${OUT_DIR}" ${PUBLISH} >> "${LOG}" 2>&1
    rc=$?
    echo "$(date -Iseconds) EXIT=${rc} season=${season}" | tee -a "${LOG}"
    if [ "${rc}" -eq 0 ]; then
        mkdir -p "${OUT_DIR}/${TAG}"
        touch "${marker}"
    else
        overall_rc="${rc}"
        failed+=("${season} (rc=${rc})")
        echo "$(date -Iseconds) WARNING season=${season} did not exit cleanly -- will retry on next run" | tee -a "${LOG}"
    fi
    sleep 5   # keep a fresh per-process rate window from stacking on the last one's tail
done

if [ ${#failed[@]} -gt 0 ]; then
    echo "$(date -Iseconds) BACKFILL DONE mode=${MODE} WITH FAILURES: ${failed[*]}" | tee -a "${LOG}"
else
    echo "$(date -Iseconds) BACKFILL DONE mode=${MODE}" | tee -a "${LOG}"
fi
# Aggregate status, not `$?` of the preceding echo -- this line is grepped to
# decide whether the run worked, so a marker that always reads 0 is a trap.
echo "EXIT=${overall_rc}" | tee -a "${LOG}"
exit "${overall_rc}"
