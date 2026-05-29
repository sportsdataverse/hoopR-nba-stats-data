# hoopR-nba-stats-data Copilot Instructions

## Project Context

This repo is the R-side NBA Stats API scrape + persistence stage for the
hoopR ecosystem. It hits `stats.nba.com` directly (through a rotating
proxy pool), writes per-season schedules and per-game play-by-play to
disk under `nba_stats/`, and commits the results to `main`. Output here
is consumed by `hoopR`'s `load_nba_*()` family via
`sportsdataverse-data` releases.

- **Package (DESCRIPTION):** `hoopR.nba` v0.0.1
- **License:** CC BY 4.0
- **Pipeline:** `NBA Stats API -> hoopR-nba-stats-data [HERE] -> sportsdataverse-data -> hoopR`

Do not confuse with `hoopR-nba-raw` / `hoopR-nba-data` — those are the
ESPN-sourced sibling repos. NBA Stats is a separate data source with
different schemas, rate limits, and auth requirements.

## Repository Workflow

- Branch from `main`; `main` is the default and release branch.
- The CI entry point is `scripts/daily_nba_stats_scraper.sh -s <START> -e <END> -r <true|false>`.
- The per-season commit subject **must** be `NBA Stats Update (Start: YYYY End: YYYY)` — downstream tooling parses years out of it.
- The repo is not a CRAN package — no `devtools::document()` flow, no NAMESPACE/man maintenance. `DESCRIPTION` exists for dependency declaration and citation only.
- Don't reorganize the `nba_stats/` output tree without aligning `hoopR`'s `load_nba_*()` loaders.

## Build & Development Commands

```sh
# CI entry point (loops seasons, scrapes schedules + PBP, commits per season)
bash scripts/daily_nba_stats_scraper.sh -s 2025 -e 2025 -r false

# Or run scrapers directly
Rscript R/nba_stats_01_scrape_schedules.R              -s 2025 -e 2025 -r false
Rscript R/nba_stats_02_scrape_pbp.R                    -s 2025 -e 2025 -r false
Rscript R/nba_stats_02_scrape_pbp_to_lineup.R          -s 2025 -e 2025 -r false
Rscript R/nba_stats_03_scrape_boxscoretraditionalv2.R  -s 2025 -e 2025 -r false
Rscript R/nba_stats_draftcombinedrillresults.R
```

`-r true` forces re-scrape; `-r false` skips files already on disk. Outputs:

- `nba_stats/schedules/{rds,csv,parquet,qs}/nba_stats_schedule_{season}.{ext}`
- `nba_stats/pbp/{rds,csv,parquet}/nba_stats_pbp_{season}.{ext}`
- `nba_stats/json/pbp/{season}/{game_id}.json` — raw NBA Stats per-game payloads
- `nba_stats/nba_stats_schedule_master.{rds,csv,parquet}` — multi-season master index

## Season Encoding

NBA seasons are indexed by **start year** in the CLI flags and on disk
(`nba_stats_schedule_2024.parquet` = 2024-25). Internally scrapers shift
via `years_vec <- (opt$s - 1):(opt$e - 1)` to align with NBA Stats' season
parameter format. That asymmetry is intentional.

Defaults pull from `hoopR:::most_recent_nba_season()`, so calling a
scraper without `-s`/`-e` scrapes the current league year.

## Code Style

- R 4.0.0+, snake_case, 2-space indent.
- Legacy magrittr pipes (`%>%`) throughout — match local style.
- Each `R/nba_stats_*.R` script is a standalone CLI: top-level `library()`
  calls, `optparse` block, then scrape logic. No package exports.
- Use `purrr::pluck()` + `%||%` for null-safe JSON parsing.
- For schema drift, prefer `dplyr::select(dplyr::any_of(...))` over bare
  selects so dropped columns don't break the script.

## HTTP / Proxy Layer

`R/utils.R` exposes `get_proxy_ips()` and `select_proxy()`, which pull a
rotating IP pool from a private endpoint. Wired via GitHub secrets:

- `PROXY_KEY`, `PROXY_PKG`, `PROXY_ENDPOINT`

Production NBA Stats calls always route through the proxy (the API
rate-limits raw GitHub Actions IPs hard). Local dry-runs without the
secrets fall through to direct calls and will eventually 429. Never
commit a proxy credential.

## Workflow

`.github/workflows/daily_nba_stats.yml` runs every cron-gated day at
`0 7 UTC` across the NBA in-season windows (late Oct, Nov-Dec, Jan-Jun,
plus full July for postseason/draft). `workflow_dispatch` inputs:
`start_year`, `end_year`, `rescrape` (default `true`).

The workflow currently invokes `scripts/daily_wnba_scraper.sh` — a known
copy-paste artifact. The correct script is `scripts/daily_nba_stats_scraper.sh`.

## Cross-Repo References

- Downstream package: <https://github.com/sportsdataverse/hoopR>
- ESPN sibling repos: <https://github.com/sportsdataverse/hoopR-nba-raw>, <https://github.com/sportsdataverse/hoopR-nba-data>
- Release artifacts: <https://github.com/sportsdataverse/sportsdataverse-data/releases>

## Commit Convention

- **Scheduled scrape commits**: `NBA Stats Update (Start: YYYY End: YYYY)` (verbatim — load-bearing).
- **Code / infra**: Conventional Commits — `type(scope): description`. Common types: `feat`, `fix`, `chore`, `ci`, `docs`, `refactor`. Use `type!:` or a `BREAKING CHANGE:` footer for breaking changes.

**Important: Never include AI agents or assistants (e.g., Claude, Copilot, Cursor, GPT, Gemini) as co-authors on commits.** Omit all `Co-Authored-By` trailers referencing AI tools.
