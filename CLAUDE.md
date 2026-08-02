# CLAUDE.md — hoopR-nba-stats-data

R-side scraper + on-disk cache for the **NBA Stats API** (`stats.nba.com`) — schedules
and per-game play-by-play. Pairs with the placeholder `hoopR-nba-stats-raw` (raw JSON
would split out there if activated); distinct from the ESPN-sourced `hoopR-nba-raw` /
`hoopR-nba-data`. Output is consumed downstream by the **hoopR** R package via
`load_nba_*()` (through `sportsdataverse-data` releases). Package `hoopR.nba` v0.0.1,
CC BY 4.0. Authors: Saiem Gilani (cre); Jason Lee, Billy Fryer, Ross Drucker (ctb).

## Commands (verified)

```sh
# CI entry point: loops seasons, runs schedules then pbp, commits + pushes per script
bash scripts/daily_nba_stats_scraper.sh -s 2025 -e 2025 -r false

# Direct R entry points (each is a standalone optparse CLI; same -s/-e/-r flags)
Rscript R/nba_stats_01_scrape_schedules.R              -s 2025 -e 2025 -r false
Rscript R/nba_stats_02_scrape_pbp.R                    -s 2025 -e 2025 -r false
Rscript R/nba_stats_02_scrape_pbp_to_lineup.R          -s 2025 -e 2025 -r false
Rscript R/nba_stats_03_scrape_boxscoretraditionalv2.R  -s 2025 -e 2025 -r false
Rscript R/nba_stats_draftcombinedrillresults.R         # ad-hoc / annual
```

Flags: `-s`/`-e` start/end year (default `hoopR:::most_recent_nba_season()`),
`-r`/`--rescrape` (`false` skips on-disk files, `true` re-fetches). R >= 4.0.0.

## Conventions

- The scrapers do **not** build stats.nba.com requests themselves — they call
  `hoopR::nba_schedule()` / `hoopR::nba_pbp()`, which own the UA/referer/headers.
  This repo adds only the `proxy=` arg and the `rate_limit()` throttle. NBA Stats
  schema drift is fixed in the **hoopR SDK**, not here.
- **Season = start year** on disk; scripts shift internally via
  `years_vec <- (opt$s - 1):(opt$e - 1)` to hit NBA Stats' season-end param. Intentional
  asymmetry — do not "fix" it.
- One-file-per-task R scripts: boilerplate `library()` block, `optparse`, then logic.
  No package exports / no `devtools::document()`. `source("R/utils.R")` for shared helpers.
- Daily commit subject `NBA Stats Update (Start: YYYY End: YYYY)` is **load-bearing** —
  downstream daily-update tooling parses the years out of it (`scraper_commit_format_loadbearing`).
- Pipe style: magrittr `%>%`, 2-space indent, snake_case. Never add AI co-author trailers to commits.

## Inputs / Outputs

- **Input:** NBA Stats API via hoopR. **Output committed to git** (the intentional SDV pattern).
- Raw per-game JSON: `nba_stats/json/pbp/{padded_game_id}.json` (flat, ~1300 files/season).
- Aggregates: `nba_stats/pbp/{csv,rds,parquet}/play_by_play_{season}.*` (csv is `.csv.gz`),
  `nba_stats/schedules/{csv,rds,parquet,qs}/schedule_{season}.*`,
  `nba_stats/nba_stats_schedule_master.{csv,rds,parquet}`.
- `run_and_commit()` commits each script's output independently (schedules first, pbp last)
  so a slow/empty-cache pbp pass can't block the schedule commit.

### Python v3 reshaper (`python/nba_data_build/reshape/`, PR #18)
- Separate build+publish path that rebuilds the classic `nba_stats_*` release
  datasets from the **unified raw store** in the sibling `hoopR-nba-stats-raw`
  (`nba_stats/json/{endpoint}/{season}/`), reading the **v3** endpoints. Full
  replacement, not parity — the v3 schema is the new contract. Mirrors the WNBA
  reshaper (`wehoop-wnba-stats-data`).
- Entry: `python -m nba_data_build.reshape --root <store> --seasons … --publish`,
  or the sdv-orch-facing wrapper `scripts/daily_nba_stats_python_processor.sh -s -e`.
  **Droplet-safe** (reads committed JSON, uploads via `gh`, no stats.nba.com calls)
  — it is the `data.build_py` stage in sdv-orch's `nba_stats` pipeline.
- Ships **parquet + rds + csv** to 15 `nba_stats_*` tags (`hoopR_data` rds stamp).
  Season-dir split: **league endpoints key by start-year, game endpoints by
  end-year** (`season_of=start+1`). `lineups` floor 2007; history 1996–2025.
  **These tags have no hoopR loader** — `load_nba_*` read ESPN tags; the
  `nba_stats_*` tags are a standalone product (see memory `nba_stats_tags_standalone`).
- **Draft is NOT built yet:** `drafthistory` is uncaptured in `-raw` (0 files) and
  needs a live stats.nba.com scrape off-droplet. The other 14 datasets are complete.
- The R scrapers above remain the **capture** path; the reshaper is the **build+publish**
  path from that captured raw.

## Model registry

A row here is mandatory for every new published model/artifact family; "frozen"
is a valid cadence but must be stated explicitly.

| model | artifact(s) | release tag | training data (seasons/source) | fitting script | gates at publish | last retrain | cadence |
|---|---|---|---|---|---|---|---|
| `nba_player_impact` (RAPM / adj-RAPM / SPM / BPM / DARKO / WAR; one row per player-season-season_type, Regular Season + Playoffs, PlayIn excluded) | `nba_player_impact_{season}.parquet` + `.csv` + `.rds` per season, plus `nba_player_impact_card.json` model card | `nba_player_impact` on `sportsdataverse/sportsdataverse-data` | 1997–2026 END-years (30 seasons): stats.nba.com possessions + player game logs, built offline from the committed `hoopR-nba-stats-raw` store (`--raw-store-dir`, PRs #19/#21) | `python/nba_model_publish/builders.py` (`build_nba_player_impact`) via `python -m nba_model_publish impact`; launcher `scripts/run_impact_backfill.sh` | TODO — no formal in-repo gate; the model card attests seasons/rows actually built (upstream validation lives in sdv-py's model zoo) | 2026-07-28 (full 1997–2026 backfill publish) | manual (droplet/residential runbook — no CI publish workflow) |

## Runbook scripts (not dead code)

- `scripts/leaguedash_backfill.sh` — multi-hour resumable full-history leaguedash
  backfill (`.done_<season>` sentinels, publishes after every season); run directly
  from a residential terminal. Referenced by nothing in-repo by design — it is a
  user-executed runbook, not pipeline wiring.
- `python/warm_possession_cache.py` — pre-backfill runbook stage despite the
  one-off-looking name: `scripts/P0_DROPLET_RUNBOOK.md` §4a "Parallel cache warm"
  runs it to warm the per-game possession cache so the sequential impact build
  (§4b) is CPU-only.

## Gotchas — NBA Stats headers / rate-limit / proxy

- `R/utils.R` `rate_limit()` is a **trailing-window token bucket** over the shared
  stats.nba.com budget (empirically ~200-300 req / 10 min of *any* type). Tunable via env
  (CI sets them in `daily_nba_stats.yml`): `STATS_RATE_MAX`=250, `STATS_RATE_WINDOW`=600s,
  `STATS_RATE_HITS`=3 (each pbp game budgeted as ~3 endpoint hits). It sleeps until a
  request fits, then records it. Called before every pbp game.
- **Fetch loop must stay sequential** — the comment explicitly forbids `furrr`/`future_map`:
  parallel workers fire simultaneous requests that blow the shared budget, and the limiter
  state lives only in the main process. (The `furrr` parallel path was removed.)
- Proxies pulled from a private endpoint by `get_proxy_ips()` (`PROXY_KEY`, `PROXY_PKG`,
  `PROXY_ENDPOINT` — GitHub secrets, wired via Actions env only; **never commit them**).
  pbp uses `next_proxy()` (round-robin, random start permutation); schedules use
  `select_proxy()` (random pick). `httr::RETRY` is used only inside `get_proxy_ips()`,
  not the data fetch. Without secrets, calls go direct and eventually 429.
- Workflow `.github/workflows/daily_nba_stats.yml`: cron `0 7 UTC` gated to in-season
  windows (Oct 18-31, Nov-Dec, Jan-Jun, full-July tail); `workflow_dispatch` takes
  `start_year`/`end_year`/`rescrape`. Correctly invokes `scripts/daily_nba_stats_scraper.sh`.
- `R/utils.R` top wipes globals then `library()`s everything — keep scripts as separate
  `Rscript` invocations, never `source()` one from another in a live session.
