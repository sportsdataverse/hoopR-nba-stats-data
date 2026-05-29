# CLAUDE.md — hoopR-nba-stats-data Development Guide

## Repo Overview

`hoopR-nba-stats-data` is the R-side scraper/persistence layer for **NBA Stats
API** play-by-play and schedule data (source: `stats.nba.com`). It pulls
per-season schedules, then per-game play-by-play JSON via the NBA Stats
endpoints, persists them to disk under `nba_stats/`, and commits the results
back to this repo. The output here is the authoritative NBA Stats cache for
the hoopR ecosystem — distinct from the ESPN-sourced `hoopR-nba-data` repo.

- **Package (from DESCRIPTION):** `hoopR.nba` (v0.0.1)
- **License:** CC BY 4.0
- **Upstream consumer:** `hoopR` (via `load_nba_*()` loaders pointing at
  `sportsdataverse-data` releases)
- **Authors:** Saiem Gilani (cre); Jason Lee, Billy Fryer, Ross Drucker (ctb)

## Pipeline Position

```
NBA Stats API (stats.nba.com) --[R scrape]--> hoopR-nba-stats-data [HERE]
                                                    | push to main
                                                    v
                                              sportsdataverse-data releases
                                                    | piggyback
                                                    v
                                                  hoopR R package (load_nba_*)
```

Sister repos for context:

- `hoopR-nba-raw` — Python ESPN scrape cache
- `hoopR-nba-data` — R-side ESPN parser/release builder
- `hoopR-mbb-raw` / `hoopR-mbb-data` — men's college basketball pair
- `hoopR-kp-data` — KenPom cache

This repo is the only one in the hoopR family that talks to NBA Stats
directly. Fix NBA Stats API drift here (or in the `hoopR` SDK if the
breaking change is in a shared helper like `most_recent_nba_season()`).

## Build & Development Commands

The repo is driven by `scripts/daily_nba_stats_scraper.sh`, which sequences
schedule scrape then per-game PBP scrape then commit + push per season:

```sh
# Full daily flow for one or more seasons (CI entry point)
bash scripts/daily_nba_stats_scraper.sh -s 2025 -e 2025 -r false

# Or call the R scrapers directly when iterating
Rscript R/nba_stats_01_scrape_schedules.R              -s 2025 -e 2025 -r false
Rscript R/nba_stats_02_scrape_pbp.R                    -s 2025 -e 2025 -r false
Rscript R/nba_stats_02_scrape_pbp_to_lineup.R          -s 2025 -e 2025 -r false
Rscript R/nba_stats_03_scrape_boxscoretraditionalv2.R  -s 2025 -e 2025 -r false

# Annual / ad-hoc scrapes
Rscript R/nba_stats_draftcombinedrillresults.R
```

Every R entry point uses `optparse` with the same canonical flags:

- `-s` / `--start_year` — season start year (e.g. `2025` for the 2024-25
  season; internally `years_vec <- (start - 1):(end - 1)` so the season is
  keyed by the **start** of the league year)
- `-e` / `--end_year`   — season end year (same convention)
- `-r` / `--rescrape`   — `true` forces re-scrape; `false` skips files
  already on disk

Defaults come from `hoopR:::most_recent_nba_season()` so omitting the
flags runs the current season only.

Output paths the scrapers write under:

- `nba_stats/schedules/{rds,csv,parquet,qs}/nba_stats_schedule_{season}.{ext}`
- `nba_stats/schedules/json/{season}/{game_id}.json` — per-game schedule snapshots
- `nba_stats/pbp/{rds,csv,parquet}/nba_stats_pbp_{season}.{ext}` — compiled PBP
- `nba_stats/json/pbp/{season}/{game_id}.json` — raw NBA Stats per-game payloads
- `nba_stats/nba_stats_schedule_master.{rds,csv,parquet}` — multi-season master index

## Repo Layout

```
R/
  nba_stats_01_scrape_schedules.R              # ESPN-style schedule scrape via NBA Stats
  nba_stats_02_scrape_pbp.R                    # Per-game PBP scrape -> nba_stats/json/pbp/
  nba_stats_02_scrape_pbp_to_lineup.R          # PBP -> lineup-state derivation
  nba_stats_03_scrape_boxscoretraditionalv2.R  # boxscoretraditionalv2 endpoint
  nba_stats_draftcombinedrillresults.R         # Annual draft combine pull
  utils.R                                      # get_proxy_ips(), select_proxy() — proxy helpers
scripts/
  daily_nba_stats_scraper.sh                   # CI entry point (sequences 01 + 02 + commit)
nba_stats/                                     # Committed scraped output (consumed downstream)
  schedules/  pbp/  json/  nba_stats_schedule_master.*
.github/workflows/
  daily_nba_stats.yml                          # Cron + workflow_dispatch
DESCRIPTION                                    # Package metadata; declares hoopR.nba deps
requirements.txt                               # Python deps (light; mostly R-driven)
```

## Daily Umbrella Workflow

`.github/workflows/daily_nba_stats.yml` is the in-repo cron entry point. It
runs the full schedule + PBP scrape sequence on a single GitHub Actions job
and commits the cumulative output in one push per season.

- **Cadence**: `0 7 UTC` daily, gated to the NBA in-season month/day
  windows: late October (`18-31`), November-December, January-June, plus a
  full-July sweep for postseason/draft tail (`1-12 7 *`).
- **Manual run**: `workflow_dispatch` accepts `start_year`, `end_year`,
  and `rescrape` (default `true`) inputs.
- **Scripts run, in order** (per season in `scripts/daily_nba_stats_scraper.sh`):
  `nba_stats_01_scrape_schedules.R`, `nba_stats_02_scrape_pbp.R`. The
  shell loop drives commits per-season with the canonical message
  `"NBA Stats Update (Start: $i End: $i)"` — that exact format is the
  contract for any downstream daily-update tooling that parses the years
  out of commit messages.
- **Proxy support**: `R/utils.R` exposes `get_proxy_ips()` / `select_proxy()`
  which pull a rotating IP pool from a private endpoint (`PROXY_KEY`,
  `PROXY_PKG`, `PROXY_ENDPOINT` env vars wired in via GitHub secrets).
  NBA Stats rate-limits aggressively, so production scrapes always go
  through the proxy — local dry-runs without the secrets fall back to
  direct calls and will eventually 429.

## Key Conventions

- **R 4.0.0+** required. Pulls heavy data deps (`arrow`, `data.table`,
  `furrr`, `progressr`, `Rcpp`, `RcppParallel`). Keep `DESCRIPTION` lean —
  this repo is not a CRAN target.
- **Season encoding**: NBA seasons are indexed by **start year**, both on
  disk (`nba_stats_schedule_2024.parquet` = 2024-25 season) and in CLI flags
  (`-s 2025` works through `hoopR:::most_recent_nba_season()` to scrape the
  current league year). The scrapers internally shift via
  `years_vec <- (opt$s - 1):(opt$e - 1)` to align with NBA Stats' season-end
  parameter format; that asymmetry is intentional, do not "fix" it.
- **JSON-on-disk is load-bearing**: Downstream `hoopR` reads raw NBA Stats
  payloads from `nba_stats/json/pbp/{season}/{game_id}.json` URLs. Don't
  reorganize the `nba_stats/` tree without coordinating with `hoopR`'s
  `load_nba_pbp()` / `load_nba_schedule()` family.
- **One-file-per-task R scripts**: each `nba_stats_0X_*.R` file is a
  standalone CLI tool (boilerplate library calls, optparse block, then
  scrape logic). No package R/ exports; no `devtools::document()` flow.
- **Null safety**: Pull-side parsing uses `purrr::pluck()` chains with the
  occasional `%||%` fallback. NBA Stats result-set headers occasionally
  drift; if a column disappears, prefer `dplyr::select(dplyr::any_of(...))`
  over bare-name selects.
- **Pipe style**: legacy `%>%` (magrittr), 2-space indent, snake_case.

## Cross-Repo References

- Downstream R package: <https://github.com/sportsdataverse/hoopR>
- ESPN sibling: <https://github.com/sportsdataverse/hoopR-nba-data>
- Raw ESPN cache: <https://github.com/sportsdataverse/hoopR-nba-raw>
- Release tags: <https://github.com/sportsdataverse/sportsdataverse-data/releases>

## Project-Specific Gotchas

- Per-season commits land via `bash scripts/daily_nba_stats_scraper.sh`,
  which loops seasons and commits with the canonical
  `NBA Stats Update (Start: YYYY End: YYYY)` subject. **Don't break this
  format** — downstream daily-update tooling parses the years out of the
  commit message (see SDV `scraper_commit_format_loadbearing` memory note).
- The workflow currently invokes `scripts/daily_wnba_scraper.sh` in
  `daily_nba_stats.yml` (copy-paste artifact) — that's a known issue.
  Local runs should use `scripts/daily_nba_stats_scraper.sh`. Fix the
  workflow path before relying on CI for fresh seasons.
- NBA Stats rejects unauthenticated bulk scrapes; the proxy pool is
  mandatory in CI. Never commit a proxy IP/credential — the secrets get
  wired through GitHub Actions env vars only.
- The `nba_stats/json/pbp/{season}/` tree grows ~1300 files/season.
  Watch repo size before adding new per-game endpoints; prefer Parquet
  aggregates for derived datasets.
- `R/utils.R` calls `rm(list = ls())` and `gc()` at the top, then
  `library()` everything. Every script does the same. Sourcing one script
  from another inside a single R session will wipe globals — keep them as
  separate `Rscript` invocations.

## Commit Convention

Use the SportsDataverse data-repo convention:

- **Daily / scheduled scrape commits**: `NBA Stats Update (Start: YYYY End: YYYY)` (load-bearing — keep verbatim)
- **Code / infra changes**: [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(scrape): add boxscoredefensivev2 endpoint to nba_stats_03
fix(scrape): retry HTTP 429s in nba_stats_02_scrape_pbp with proxy rotation
chore(deps): bump arrow pin in DESCRIPTION
ci: align daily_nba_stats.yml entry point with daily_nba_stats_scraper.sh
```

Prefer scoped subjects (`feat(scrape): ...`, `ci(workflow): ...`). Use
`type!:` or a `BREAKING CHANGE:` footer for breaking changes. Split
unrelated work into separate commits for reviewability.

**Important: Never include AI agents or assistants (e.g., Claude, Copilot, Cursor, GPT, Gemini) as co-authors on commits.** Omit all `Co-Authored-By` trailers referencing AI tools. The human author is the sole attributable contributor regardless of how AI was used in the work.
