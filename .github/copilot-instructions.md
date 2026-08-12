# hoopR-nba-stats-data Copilot Instructions

## Project Context

This repo is the NBA Stats API **reshape + publish** stage for the hoopR
ecosystem. It reads the committed raw JSON store in the sibling
`hoopR-nba-stats-raw`, compiles per-season datasets under `nba_stats/`, and
commits + publishes them. Output is consumed by `hoopR`'s `load_nba_*()`
family via `sportsdataverse-data` releases.

> **It does not scrape. Python is the primary producer** —
> `python/nba_data_build/`. `scripts/daily_nba_stats_scraper.sh` was deleted at
> the Python cutover and the daily job is Python-only.
>
> **`R/` is neither empty nor dead — DO NOT DELETE IT.** This file claimed it
> was emptied (wrong: the six files are tracked), and a 2026-08-06 correction
> then called them "dead code pending a deliberate delete" (also wrong, and
> more dangerous). The real history: `0b46970b` retired the R chain,
> `960bdadf` **reverted that** — *"restore the R stage chain as the
> methodological twin."* Standing policy (2026-08-03) is that a `-data` repo
> carries BOTH pipelines: Python primary and getting the work, R maintained
> alongside as the methodological/language equivalent, both moving together.
>
> So `nba_stats_01_scrape_schedules.R`, `02_scrape_pbp.R`,
> `02_scrape_pbp_to_lineup.R`, `03_scrape_boxscoretraditionalv2.R`,
> `nba_stats_draftcombinedrillresults.R` and `utils.R` are the retained R side.
> No workflow invokes them, and that is the intended state — keeping the twin
> preserves the METHOD in a second language, it does not re-schedule R. Not
> being on a cron is not evidence of deadness. If you add or remove a dataset
> on the Python side, the R side moves with it.
>
> **Never run an R stage to inspect its output**: they call
> `sportsdataverse_save()` with no dry-run gate and publish to the LIVE
> release.
>
> `hoopR-nba-stats-raw` is **not a placeholder**: it holds the 1996–2026 raw
> capture this repo reads.

- **Package (DESCRIPTION):** `hoopR.nba` v0.0.1 (vestigial — not an R pipeline)
- **License:** CC BY 4.0
- **Pipeline:** `NBA Stats API -> hoopR-nba-stats-raw -> hoopR-nba-stats-data [HERE] -> sportsdataverse-data -> hoopR`

Do not confuse with `hoopR-nba-raw` / `hoopR-nba-data` — those are the
ESPN-sourced sibling repos. NBA Stats is a separate data source with
different schemas, rate limits, and auth requirements.

## Repository Workflow

- Branch from `main`; `main` is the default and release branch.
- The CI entry point is `.github/workflows/daily_nba_stats.yml`, which calls
  `scripts/daily_nba_stats_python_processor.sh -s <START> -e <END>`.
- The per-season commit subject **must** be `NBA Stats Update (Start: YYYY End: YYYY)` — downstream tooling parses years out of it.
- The repo is not a CRAN package — no `devtools::document()` flow, no NAMESPACE/man maintenance. `DESCRIPTION` exists for dependency declaration and citation only.
- Don't reorganize the `nba_stats/` output tree without aligning `hoopR`'s `load_nba_*()` loaders.

## Build & Development Commands

```sh
# Daily flow (the workflow calls this same script; loops seasons, commits per season)
bash scripts/daily_nba_stats_python_processor.sh -s 2025 -e 2025

# Direct reshape
python -m nba_data_build.reshape --root <hoopR-nba-stats-raw>/nba_stats/json --seasons 2025

# Runbook helpers
bash scripts/hydrate_raw_store.sh                  # clone-free hydrate of the raw store
bash scripts/leaguedash_backfill.sh                # checkpointed; .done_<season> on rc 0
bash scripts/run_impact_backfill.sh                # nba_player_impact full-history
bash scripts/run_v3_backfill.sh -s 1997 -e 2026    # Program V v3 backfill (resumable)
bash scripts/run_v3_cutover.sh -s 1997 -e 2026     # D26d cutover -- DRY RUN by default
python python/warm_possession_cache.py 2000:2024   # warm the possession cache
```

`scripts/run_v3_backfill.sh` stages v3 `schedule`/`pbp`/`possessions`/`lineups`
into `v3_staging/` (never clobbering the live tree) and is verified by
`python -m nba_data_build.v3_gate`; it is operator-run, not workflow-wired.

`scripts/run_v3_cutover.sh` (`python -m nba_data_build.v3_cutover`) publishes
those staged parquets onto the production release tags — the D26d cutover. It is
**a dry run unless `-x` is passed**: it re-runs the §10.3 gate, writes a REPLACE
MANIFEST into `logs/` naming every asset it would overwrite (with the current
remote size + updated-at), and uploads nothing. The gate hard-aborts on any
unexplained `DIFF`; explained cases are allowlisted one at a time with
`--allow-diff SEASON:FAMILY` and printed in the manifest. Uploads are per-file
with a post-upload size verification, resumable via
`v3_staging/.cutover_receipts.json`. Retiring the `_v3` tags is a separate
invocation (`-R`), never bundled with the data upload. Operator-run, not
workflow-wired.

`HOOPR_NBA_STATS_RAW_ROOT` overrides the raw store (a local checkout or a
raw.githubusercontent URL); `HOOPR_NBA_STATS_PYBIN` the interpreter. The driver
fails fast when the store has no `playbyplayv3/` — otherwise it would compile
zero games and report success. Outputs:

- `nba_stats/schedules/{rds,csv,parquet,qs}/nba_stats_schedule_{season}.{ext}`
- `nba_stats/pbp/{rds,csv,parquet}/nba_stats_pbp_{season}.{ext}`
- `nba_stats/json/pbp/{season}/{game_id}.json` — raw NBA Stats per-game payloads
- `nba_stats/nba_stats_schedule_master.{rds,csv,parquet}` — multi-season master index

## Season Encoding

NBA seasons are indexed by **end year** (`2026` = 2025-26) — the workflow
comment says so explicitly and derives the default with an October rollover
(`month <= 9` → previous year, then `+1`). This section previously claimed
**start year**; that inversion is the kind that silently labels a whole season
wrong, so treat the workflow's rule as the source of truth.

Two documented exceptions:

- The **season-level** half of the raw store keys its dirs by start year
  (`{endpoint}/2023/` holds 2023-24).
- Several stats.nba.com endpoints require the span spelling `"2023-24"` and
  return a silent zero-row frame for a bare year. That spelling is owned by the
  shared engine (`sportsdataverse.scrape.stats`, league-keyed), not here.

Calling the driver without `-s`/`-e` builds the current league year.

## Code Style

- polars 1.x modern API only; snake_case; typed new modules.
- Read the raw store, reshape, write — no HTTP in this repo.
- For schema drift, select defensively so a dropped upstream column doesn't
  break the build.

## HTTP / Proxy Layer

**None here.** Capture belongs to `hoopR-nba-stats-raw`, whose scrape layer is
the shared `sportsdataverse.scrape.stats` engine. Two facts that matter if you
are chasing a capture bug there rather than a reshape bug here:

- `stats.nba.com` **TLS/JA3-fingerprint-blocks plain `requests`** — the symptom
  is a silent timeout, not a refusal. The engine uses `curl_cffi` with
  `impersonate="chrome"`.
- The proxy pool and rate knobs are env-only (`STATS_RATE_*`), never hardcoded.

Never commit a proxy credential.

## Workflow

`.github/workflows/daily_nba_stats.yml` runs every cron-gated day at
`0 7 UTC` across the NBA in-season windows (late Oct, Nov-Dec, Jan-Jun,
plus full July for postseason/draft), calling
`scripts/daily_nba_stats_python_processor.sh`. `workflow_dispatch` inputs:
`start_year`, `end_year`.

`.github/workflows/nba_models.yml` is the separate, dispatch-only model publish
(`dry_run` defaults true); full-history backfills stay on the droplet runbook
(`scripts/P0_DROPLET_RUNBOOK.md`). See the model registry in the README.

## Cross-Repo References

- Downstream package: <https://github.com/sportsdataverse/hoopR>
- ESPN sibling repos: <https://github.com/sportsdataverse/hoopR-nba-raw>, <https://github.com/sportsdataverse/hoopR-nba-data>
- Release artifacts: <https://github.com/sportsdataverse/sportsdataverse-data/releases>

## Commit Convention

- **Scheduled scrape commits**: `NBA Stats Update (Start: YYYY End: YYYY)` (verbatim — load-bearing).
- **Code / infra**: Conventional Commits — `type(scope): description`. Common types: `feat`, `fix`, `chore`, `ci`, `docs`, `refactor`. Use `type!:` or a `BREAKING CHANGE:` footer for breaking changes.

**Important: Never include AI agents or assistants (e.g., Claude, Copilot, Cursor, GPT, Gemini) as co-authors on commits.** Omit all `Co-Authored-By` trailers referencing AI tools.
