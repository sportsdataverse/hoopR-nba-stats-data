#!/bin/bash
# Build + publish the NBA stats datasets with the Python reshaper
# (python/nba_data_build.reshape) instead of the R creation scripts.
#
# Drop-in for the R scraper's build half: same -s/-e contract, so sdv-orch's
# data.build_py stage can call it. Reads the already-committed raw store from the
# sibling hoopR-nba-stats-raw checkout, builds parquet+rds+csv, and uploads them
# to the nba_stats_* releases (creating any missing tag).
#
#   bash scripts/daily_nba_stats_python_processor.sh -s 2024 -e 2024
#
# DROPLET-SAFE: unlike the R scrape, this makes NO stats.nba.com calls -- it only
# reads local JSON and talks to `gh`. That is why it can run on the droplet where
# the scrape cannot (datacenter IP hangs on stats.nba.com).
#
# Artifacts are release-only (io.py: parquet+rds+csv all ship to tags, none are
# committed here), so this writes to a scratch dir and uploads -- no git commit.
# That is about the RESHAPED datasets. The nba_player_impact MODEL artifacts ARE
# committed, by scripts/nightly_nba_impact.sh -- see CLAUDE.md (2026-09-02).

set -uo pipefail

while getopts s:e:r: flag; do
    case "${flag}" in
        s) START_YEAR=${OPTARG};;
        e) END_YEAR=${OPTARG};;
        r) : ;;  # accepted for -s/-e/-r parity with the R processor; unused (no scrape)
        *) echo "Usage: $0 -s <start_year> -e <end_year>"; exit 1;;
    esac
done

if [ -z "${START_YEAR:-}" ] || [ -z "${END_YEAR:-}" ]; then
    echo "Usage: $0 -s <start_year> -e <end_year>"
    exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPOS_ROOT="${SDV_REPOS:-/mnt/sdv_repos}"
# The raw store lives in the -raw sibling; the CLI's --root is its json base.
# Override with HOOPR_NBA_STATS_RAW_ROOT (e.g. a raw.githubusercontent URL in CI).
RAW_ROOT="${HOOPR_NBA_STATS_RAW_ROOT:-${REPOS_ROOT}/hoopR-nba-stats-raw/nba_stats/json}"

# Venv interpreter by absolute path, not `uv run`: sdv-orch invokes this from a
# systemd unit whose PATH excludes /root/.local/bin, so `uv` exits 127 there.
# Packaging moved to the repo root (2026-08-02); the venv lives at .venv now.
PYBIN="${HOOPR_NBA_STATS_PYBIN:-${REPO_DIR}/.venv/bin/python}"

# Fail before doing anything if the raw checkout isn't where we expect. A missing
# root would build zero rows and "succeed", quietly publishing nothing. A URL
# root is passed straight through (the builders are dual-mode Path|str).
if [[ "${RAW_ROOT}" != http*://* && ! -d "${RAW_ROOT}/playbyplayv3" ]]; then
    echo "::error ::raw store not found at ${RAW_ROOT} (no playbyplayv3/ under it)"
    exit 1
fi

if [ ! -x "${PYBIN}" ]; then
    echo "::error ::python venv not found at ${PYBIN} -- run 'uv sync' in ${REPO_DIR}"
    exit 1
fi

cd "${REPO_DIR}" || exit 1
mkdir -p "${REPO_DIR}/logs"

ANY_FAILED=0
for i in $(seq "${START_YEAR}" "${END_YEAR}"); do
    LOGFILE="${REPO_DIR}/logs/hoopr_nba_stats_python_logfile_${i}.log"
    OUT_DIR="$(mktemp -d "/tmp/nba_stats_build_${i}.XXXXXX")"
    echo "=== Building NBA stats (python) for season ${i} ==="
    # A SUBSHELL, not a brace group: a group's status is its LAST command, so the
    # trailing echo masked a failing build -- PIPESTATUS[0] was always 0 and every
    # season reported success. The subshell exits with python's status instead.
    (
        echo "=== season ${i} started $(date -u +'%F %T')Z ==="
        "${PYBIN}" -m nba_data_build.reshape \
            --root "${RAW_ROOT}" \
            --seasons "${i}" \
            --out "${OUT_DIR}" \
            --publish
        py_rc=$?
        echo "EXIT=${py_rc}"
        echo "=== season ${i} finished $(date -u +'%F %T')Z ==="
        exit "${py_rc}"
    ) 2>&1 | tee -a "${LOGFILE}"
    # tee hides the subshell's exit status behind its own; recover it from PIPESTATUS[0].
    rc=${PIPESTATUS[0]}
    if [ "${rc}" -eq 0 ]; then
        # Stage 99 (spec D34), in-loop half: restamp this season's committed
        # schedule file's in_* flags from the artifacts just built, BEFORE the
        # scratch dir goes away. Non-fatal: a stamp failure must not fail the
        # publish that already happened.
        #
        # $((i + 1)), not ${i}: the two stages disagree about what a season is.
        # `nba_data_build.reshape --seasons` takes the START year (raw.store_dir
        # is the documented single point of the start<->end split), while stage
        # 99's `--season` is the END year -- its own _span reads 2026 as
        # "2025-26". Passing ${i} to both stamped the PREVIOUS season's schedule
        # file, and since the 2026-08-13 END-year republish it would also miss
        # every built artifact (reshape now writes {stem}_{i+1}). Both failures
        # are silent: a lookup miss just leaves the old flags in place.
        "${PYBIN}" python/nba_stats_99_schedule_master_creation.py \
            --built-dir "${OUT_DIR}" --season "$((i + 1))" --stamp-only \
            2>&1 | tee -a "${LOGFILE}" \
            || echo "schedule-master stamp failed for season ${i}" | tee -a "${LOGFILE}"
    fi
    rm -rf "${OUT_DIR}"
    [ "${rc}" -ne 0 ] && { echo "season ${i} FAILED (rc=${rc})"; ANY_FAILED=1; }
done

# Stage 99, union half: rebuild the master + games_in_data_repo manifest +
# coverage index from ALL committed season schedules (the whole archive, not
# just this run's window). Non-fatal for the same reason as above.
"${PYBIN}" python/nba_stats_99_schedule_master_creation.py \
    || echo "schedule-master union failed"

exit "${ANY_FAILED}"
