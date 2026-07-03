# nba_data_build

Local, incremental builder: compiles the missing recent NBA possession seasons
(via the sdv-py harness), fits RAPM, runs the validation card, and publishes to
`sportsdataverse-data` releases. Run from a **residential IP** (stats.nba.com
hangs on cloud IPs).

    cd python && uv sync
    # incremental (fills the gap through the current season), local only:
    uv run python -m nba_data_build --out build_out
    # then publish (uses your gh auth):
    uv run python -m nba_data_build --seasons 2023 2024 --out build_out --publish

Offline tests: `uv run pytest -q`. Live compile: `SDV_PY_NBA_STATS_LIVE=1 uv run pytest tests/test_live.py`.

## Notes

- **`--dry-run` still compiles.** `--dry-run` scopes only the *publish* step — it plans
  the release uploads without executing them. It does **not** skip the (potentially
  multi-hour) live season compile, so it runs `build()` first. Use it to preview a
  publish of an already-built `--out` directory, not to preview the compile.
- **The validation card is left in `--out`.** `build` writes
  `nba_rapm_validation_report.md` to the output directory; it does not commit it to the
  repo. Copy it into `docs/` and commit it manually if you want it versioned, and it can
  be referenced from the release notes.

## `pipeline` verb — NBA-Stats v3 raw store + possession pipeline

`python -m nba_data_build pipeline` runs the v3 raw-scrape → from-raw-process →
season-rollup → schedule-flags loop (Tasks 4–9), for one or more seasons, entirely
local by default:

```sh
cd python && uv sync
# dry-run: scrape (skips already-captured games) -> process -> rollup -> flags,
# all written locally under --root. NEVER commits, pushes, or uploads.
SDV_PY_NBA_STATS_LIVE=1 uv run python -m nba_data_build pipeline --seasons 2023 --root .. --dry-run
```

**Prerequisite (OD1 one-game proxy probe).** Before running this against more than
one game, confirm `stats.nba.com` is actually reachable from wherever you're running
(residential IP, or with a configured proxy pool) — it silently hangs rather than
erroring on datacenter/cloud IPs. See `nba_data_build/scrape/client.py` /
`scrape/proxy.py` and Task 5's one-game probe snippet before fanning out to a full
season. `SDV_PY_NBA_STATS_LIVE=1` gates the live `stats.nba.com` calls the same way
the rest of the test suite does.

**The dry-run is mandatory before any `--publish`.** `--dry-run` (or simply omitting
both `--dry-run` and `--publish`, which behaves the same way) performs the *entire*
local pipeline — raw JSON under `nba_stats/json/{pbpv3,boxv3,boxv3_periods}/`,
per-season parquet under `nba_stats/{pbpv3,possessions,lineups}/parquet/`, a per-season
v3 discovery+flags snapshot under `nba_stats/schedule_v3/parquet/`, and an in-place
flags upsert into the committed `nba_stats/nba_stats_schedule_master.parquet` — but
never stages, commits, pushes, or uploads anything. Inspect the outputs by hand before
ever passing `--publish`.

**`--publish` is a deliberate, controller-approved rebuild action, never a default.**
It stages the explicit `nba_stats` path (never a blind `git add -A`) and commits with
the preserved subject `NBA Stats Update (Start: {season} End: {season})` matching the
existing R-side producer's convention. `--dry-run` always wins if both flags are
passed together — `--publish` alone (no `--dry-run`) is the only combination that
reaches the publish step:

```sh
# CONTROLLER-APPROVED ONLY
SDV_PY_NBA_STATS_LIVE=1 uv run python -m nba_data_build pipeline --seasons 2022 2023 2024 2025 --root .. --publish
```

**`--target` (OD2, release-layout question — currently unresolved) picks the publish
layout per run**, so both options stay one flag away instead of requiring a decision
now:

- `--target commit` (**default**, the safer option): commits `nba_stats/*` straight to
  git.
- `--target release`: does the same commit, **and** additionally mirrors the
  per-season `pbpv3` / `possessions` / `lineups` rollups to dedicated GitHub release
  tags (`nba_stats_pbpv3` / `nba_stats_possessions_v3` / `nba_stats_lineups_v3` —
  distinct from the modeling `build` path's `nba_stats_rapm` / `nba_stats_possessions`
  tags, so the two publish flows never clobber each other's releases).

Treat any `--rescrape` or `--target release` re-publish of an already-published season
as a deliberate action, not a default. `--cache-dir` controls the local, gitignored,
per-game resumability cache (default `{root}/.nba_pipeline_cache/`) — safe to delete
between runs; it only ever speeds up a resumed `rollup_season`, never holds
authoritative data.

## Known gap: overtime period-box capture

`scrape_finished_games` currently defaults `n_periods=4` (the schedule loader carries no
period count), so `boxv3_periods` raw payloads capture regulation periods only — OT games'
period 5+ boxes are not fetched, and the `BOX_PERIODS` availability flag reflects file
presence, not period completeness. This cannot mislead today's outputs (the active lineup
path is `pbp_fallback`, which never reads `boxv3_periods`, and pbp/possessions/lineups are
complete for OT games), but it must be closed — real per-game period counts threaded into
discovery — before the `quarter_box` seam activates at the next sportsdataverse pin bump.
