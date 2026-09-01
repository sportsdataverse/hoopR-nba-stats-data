# CLAUDE.md — hoopR-nba-stats-data

Reshaper + release uploader for the **NBA Stats API** (`stats.nba.com`). Distinct
from the ESPN-sourced `hoopR-nba-raw` / `hoopR-nba-data`. Output is consumed
downstream by the **hoopR** R package via `load_nba_*()` (through
`sportsdataverse-data` releases). Package `hoopR.nba` v0.0.1, CC BY 4.0.
Authors: Saiem Gilani (cre); Jason Lee, Billy Fryer, Ross Drucker (ctb).

> **This repo does not scrape, and it is no longer R.** Capture lives in
> `hoopR-nba-stats-raw` — **not a placeholder**: it holds the committed
> 1996–2026 raw JSON store this repo reads (that claim inverted long ago and
> was corrected in that repo's own docs first). The producer here is
> `python/nba_data_build/`.
>
> **`R/` is empty.** `R/nba_stats_01_scrape_schedules.R`,
> `02_scrape_pbp.R`, `02_scrape_pbp_to_lineup.R`,
> `03_scrape_boxscoretraditionalv2.R`, `nba_stats_draftcombinedrillresults.R`
> and `scripts/daily_nba_stats_scraper.sh` were all deleted at the Python
> cutover; this file listed them under a heading reading "Commands (verified)".

## Commands

```sh
# Daily flow (the workflow calls this same script)
bash scripts/daily_nba_stats_python_processor.sh -s 2025 -e 2025

# Direct reshape (RAW_ROOT may be a local checkout or a raw.githubusercontent URL)
python -m nba_data_build.reshape --root <hoopR-nba-stats-raw>/nba_stats/json --seasons 2025

# Runbook helpers
bash scripts/hydrate_raw_store.sh          # clone-free hydrate of the raw store
bash scripts/leaguedash_backfill.sh        # league-dash cube, BUILD-ONLY; .done_<mode>_<season> on rc 0
bash scripts/leaguedash_backfill.sh -s 2026 -e 2026 -n   # ...plan uploads, upload nothing
python -m nba_data_build.leaguedash_cli --seasons 2026 --publish   # publish (deliberate)
bash scripts/run_impact_backfill.sh        # nba_player_impact full-history backfill, BUILD-ONLY
bash scripts/run_impact_backfill.sh 2025 --publish   # ...and upload to the release (deliberate)
bash scripts/run_v3_backfill.sh -s 1997 -e 2026   # Program V v3 backfill (resumable)
bash scripts/run_v3_cutover.sh -s 1997 -e 2026    # D26d cutover -- DRY RUN by default
python -m nba_data_build.warm_possession_cache 2000:2024   # warm the possession cache
```

Env: `HOOPR_NBA_STATS_RAW_ROOT` overrides the raw store location,
`HOOPR_NBA_STATS_PYBIN` the interpreter (the workflow sets both). The driver
fails fast when the raw store has no `playbyplayv3/` rather than compiling zero
games and reporting success.

**`leaguedash_backfill.sh` builds; it cannot publish.** It writes under
`build_out/` and has no upload path at all — `-n` plans a publish without
uploading, and `-p` is a usage error. It used to pass `--publish`
unconditionally and upload after every season, leaving a live release one stray
invocation away from a rewrite — the same hazard as the R creation stages that
overwrote three WNBA 2025 tags. An opt-in flag was rejected as the fix: a flag
can be typed by accident or copied out of a runbook line, whereas a script
carrying no upload path cannot publish at all. Publishing is the deliberate
module invocation
`python -m nba_data_build.leaguedash_cli --seasons <y> --publish`.
**`run_impact_backfill.sh` also builds by default, but keeps a publish path.**
`nba_model_publish impact` requires `--publish` to touch the release; without
it the run builds and exits 0. The stronger no-upload-path-at-all treatment
was rejected HERE because this publisher is wired: a daily droplet cron exists
to publish `nba_player_impact` (`scripts/P0_DROPLET_RUNBOOK.md` §6), so
removing the path would have converted a multi-hour job into a silent no-op —
worse than the accidental publish, because nothing errors. The cron and the
runbook backfill line pass `--publish`; `tests/test_impact_publish_optin.py`
pins both halves. `--dry-run` still plans the upload and beats `--publish`.

`daily_nba_stats_python_processor.sh` remains a publisher by design, so read a
script's header before running it.
`wehoop-wnba-stats-data/scripts/leaguedash_backfill.sh` is this script's twin —
change both together.

## Conventions

- **Seasons are END year** (`2026` = 2025-26), with one documented exception:
  the season-level half of the raw store keys its dirs by start year. Several
  stats.nba.com endpoints also need the span spelling `"2023-24"` and return a
  silent zero-row frame for a bare year — the shared engine owns that spelling.
- This repo makes no stats.nba.com requests. Capture bugs belong to
  `sportsdataverse.scrape.stats` (the shared engine behind both stats-raw
  twins); parsing/schema drift belongs to `sportsdataverse-py`.
- polars 1.x modern API only; snake_case.
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
  All 17 tags this repo owns (those 15 + the Program V cutover's
  `nba_stats_possessions` / `nba_stats_game_lineups`) are provisioned by
  `ops/init/0000_create_hoopr_nba_stats_releases_init.sh`. **Neither `gh release
  upload` nor `run_v3_cutover.sh -x` can CREATE a tag** — upload fails on a
  missing release and the cutover dry run cannot warn (`remote_assets()` returns
  `{}` for both "absent" and "empty"), so run the init script first whenever the
  pipeline gains a new release target.
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
| `nba_player_impact` (RAPM / adj-RAPM / SPM / BPM / DARKO / WAR; one row per player-season-season_type, Regular Season + Playoffs, PlayIn excluded) | `nba_player_impact_{season}.parquet` + `.csv` + `.rds` per season, plus `nba_player_impact_card.json` model card | `nba_player_impact` on `sportsdataverse/sportsdataverse-data` | 1997–2026 END-years (30 seasons): stats.nba.com possessions + player game logs, built offline from the committed `hoopR-nba-stats-raw` store (`--raw-store-dir`, PRs #19/#21) | `python/nba_model_publish/builders.py` (`build_nba_player_impact`) via `python -m nba_model_publish impact` (**publishing is opt-in — `--publish`, else it builds only**); launcher `scripts/run_impact_backfill.sh` (forwards `--publish`; the droplet cron passes it) | TODO — no formal in-repo gate; the model card attests seasons/rows actually built (upstream validation lives in sdv-py's model zoo) | 2026-07-28 (full 1997–2026 backfill publish) | on-demand: `nba_models.yml` (workflow_dispatch only, `dry_run` defaults true) for an incremental season; full-history backfills stay on the droplet runbook (`scripts/hydrate_raw_store.sh` + `scripts/run_impact_backfill.sh`) |

## Runbook scripts (not dead code)

- `scripts/leaguedash_backfill.sh` — multi-hour resumable full-history leaguedash
  backfill. **Build-only: it has no upload path.** `.done_<mode>_<season>`
  sentinels are keyed by mode so a build pass is never mistaken for a published
  one; `-n` plans uploads without performing them. Run directly from a
  residential terminal. Referenced by nothing in-repo by design — it is a
  user-executed runbook, not pipeline wiring.
- `scripts/hydrate_raw_store.sh` — clone-free raw-store hydrate from the
  `nba-stats-raw-json` per-season release bundles (~30 tarballs instead of ~120k
  per-file URL reads); the CI-friendly way to run a FULL-history impact build.
  Idempotent + resumable (already-extracted seasons skip). Landed with #19/#20.
- `python/nba_data_build/warm_possession_cache.py` — pre-backfill runbook stage despite the
  one-off-looking name: `scripts/P0_DROPLET_RUNBOOK.md` §4a "Parallel cache warm"
  runs it to warm the per-game possession cache so the sequential impact build
  (§4b) is CPU-only.
- `scripts/run_v3_backfill.sh` — Program V (design §9) v3 dataset backfill:
  builds `schedule`/`pbp`/`possessions`/`lineups` per season from the committed
  raw store into `v3_staging/` (which never clobbers the live tree). Resumable —
  a season whose outputs exist is skipped unless `--rebuild`. Operator-run, not
  wired to a workflow: it is a multi-hour job and its output is gated before
  adoption. Verify a run with the §9.3 diff gate, which reconciles v3 against
  legacy where both exist and against the raw store where they don't:

  **Game universe = every season type.** `leaguegamelog` was only ever captured
  at `regular-season` + `playoffs`, so it stays the metadata source where it has
  the game and `scheduleleaguev2/{START}.json` supplies the ids it never covered:
  preseason (`001`), All-Star (`003`), play-in (`005`) and the NBA Cup final
  (`006`). `season_type` is derived from the game-id type digit
  (`v3_backfill.SEASON_TYPE_OF_PREFIX`); digit `9` is an arena hold, not a game,
  and is dropped. Per-era absence is expected, not a failure — no play-in before
  2020-21, no NBA Cup before 2023-24. The gate diffs **core-to-core** (`{2,4}`)
  — both the id-set diff and the score reconciliation — and counts non-core
  staged games as `staged_noncore`, never as a `DIFF`. Points and `W`/`L` are
  filled only from a scored, decided final: an absent `score` stays null, and a
  0-0 "Final" (cancellation, unscored exhibition) gets no fabricated winner.

  **`games_no_pbp` is not `games_failed` — and is not a re-scrape target.**
  Publishing every season type means the schedule carries games upstream served
  no play-by-play for: 1,602 of 40,961 as of 2026-08-12/13, with
  `games_failed=0`. `games_failed` is a game the build could not process and is
  exit-code-worthy; `games_no_pbp` is a *valid* `playbyplayv3` response with
  `actions: []` and is the expected steady state. **Preseason play-by-play
  begins with the 2010-11 season** (END-year 2010 is 0 of 119, 2011 is 119 of
  119); the rest are All-Star exhibitions (30), never-played 2005 Finals
  placeholders (2), and the 2013-04-16 Boston Marathon cancellation (1). Each
  was re-probed live against a same-session positive control. Re-running the
  backfill will not move `games_no_pbp`; a re-capture only ever answers
  `games_uncaptured`. Full accounting: `docs/nba-v3-coverage.md`.

  ```sh
  bash scripts/run_v3_backfill.sh -s 1997 -e 2026    # prints its own tail -f watch command
  PYTHONPATH=python python/.venv/Scripts/python.exe -m nba_data_build.v3_gate -s 1997 -e 2026
  ```

  The D26d tag swap (retiring the `_v3` tags) is a separate post-gate decision.

- `scripts/run_v3_cutover.sh` — Program V (design §9, D26d) cutover publisher:
  moves the staged v3 parquets onto the **production** release tags. **A DRY RUN
  BY DEFAULT** — it re-runs the §9.3 gate, writes a REPLACE MANIFEST to `logs/`,
  and uploads nothing. Publishing needs an explicit `-x` (`--execute`), which is
  the least reversible action in the program: overwriting a release asset
  destroys the previous bytes and `hoopR::load_nba_*()` reads them.

  ```sh
  bash scripts/run_v3_cutover.sh -s 1997 -e 2026            # dry run; prints its own tail -f
  bash scripts/run_v3_cutover.sh -s 1997 -e 2026 -- --allow-diff-file ops/v3_cutover_allowlist.txt
  bash scripts/run_v3_cutover.sh -s 1997 -e 2026 -x         # PUBLISH (after reading the manifest)
  bash scripts/run_v3_cutover.sh -R -x                      # SEPARATE step: retire the _v3 tags
  bash scripts/run_v3_cutover.sh -L -x                      # SEPARATE step: retire the LEGACY assets
  ```

  **The gate allowlist is a reviewed file, not a flag you improvise.**
  `ops/v3_cutover_allowlist.txt` holds one `SEASON:FAMILY=REASON` line per
  explained §9.3 finding, each verified game-by-game against sources that are
  independent of the play-by-play (raw `leaguegamelog` PTS,
  `boxscoretraditionalv3` team totals cross-checked against the player-point
  sums, `boxscoresummaryv2` LineScore). The legacy schedule is **not** such a
  source — it inherits pbp-derived scores, so "legacy agrees with pbp" is one
  source, not two. The manifest renders every applied entry with its reason and
  marks a reason-less one `UNATTRIBUTED`. It is never applied implicitly: pass
  `--allow-diff-file`. Never allowlist a *capture* gap (a game absent from the
  raw store) — that needs a re-capture.

  **Three formats, always.** Every artifact publishes as `parquet` + `rds` +
  `csv.gz` (`nba_data_build/v3_formats.py`). `hoopR::load_nba_*()` reads the
  `.rds`, so a parquet-only publish ships data hoopR cannot open; the rds comes
  from `sportsdataverse._rds.write_rds` (byte-parity, no R / no `Rscript`) and is
  **verified by reading it back** — shape, column names, and per-column R vector
  type against the source parquet — before it can be uploaded. The csv is gzipped
  per the `ncaa-wbb-hoops-data` convention (GitHub's 2 GiB per-asset limit).

  **The publish is ADDITIVE (decision B).** The END-year assets land *next to*
  the legacy START-year ones rather than replacing them, so an all-`NEW` /
  0-`REPLACE` manifest is the intended outcome, not a defect. That leaves each
  tag carrying two labelings of the same real season — published
  `play_by_play_1996.*` IS 1996-97 and staged `nba_play_by_play_1997.*` is ALSO
  1996-97 — which the manifest's **SEASON-LABEL COLLISION** section enumerates
  per tag, and which a generated per-tag `README.md` (uploaded on `-x`) explains
  to consumers. `-L` (`--retire-legacy-assets`) removes the legacy names once
  consumers have migrated; it refuses any season whose END-year replacement is
  not present and byte-verified on the tag **in every format**, and is never
  bundled with an upload or with `-R`.

  **The v3 per-game lineups publish to `nba_stats_game_lineups`** (decision 3),
  not `nba_stats_lineups` — the latter carries the season-level
  `leaguedashlineups` dataset from stage 04, a different dataset rather than an
  older version, and is left untouched.

  Read the manifest's **WOULD BE DESTROYED** and **SURVIVES UN-REPLACED**
  sections before ever passing `-x`. The gate hard-aborts on any unexplained
  `DIFF`; each explained case needs its own `--allow-diff SEASON:FAMILY`, which
  is echoed into the manifest — there is no blanket ignore switch. Uploads are
  one asset at a time with a size re-check after each, and stop on the first
  mismatch (`gh release upload` with many files has silently dropped large
  assets). Verified uploads are recorded in `v3_staging/.cutover_receipts.json`,
  so a re-run skips them: the publish is resumable and idempotent.

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

## Datasets

<!-- BEGIN GENERATED: datasets -->
| Script | Dataset | Release tag | Last published |
|---|---|---|---|
| [`python/nba_stats_01_standings_creation.py`](python/nba_stats_01_standings_creation.py) | [`standings`](docs/datasets/standings.md) | [`nba_stats_standings`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_standings) | 2026-07-24 |
| [`python/nba_stats_02_player_season_stats_creation.py`](python/nba_stats_02_player_season_stats_creation.py) | [`player_season_stats`](docs/datasets/player_season_stats.md) | [`nba_stats_player_season_stats`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_player_season_stats) | 2026-07-24 |
| [`python/nba_stats_03_team_season_stats_creation.py`](python/nba_stats_03_team_season_stats_creation.py) | [`team_season_stats`](docs/datasets/team_season_stats.md) | [`nba_stats_team_season_stats`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_team_season_stats) | 2026-07-24 |
| [`python/nba_stats_04_lineups_creation.py`](python/nba_stats_04_lineups_creation.py) | [`lineups`](docs/datasets/lineups.md) | [`nba_stats_lineups`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_lineups) | 2026-07-24 |
| [`python/nba_stats_05_rosters_creation.py`](python/nba_stats_05_rosters_creation.py) | [`rosters`](docs/datasets/rosters.md) | [`nba_stats_rosters`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_rosters) | 2026-07-24 |
| [`python/nba_stats_06_coaches_creation.py`](python/nba_stats_06_coaches_creation.py) | [`coaches`](docs/datasets/coaches.md) | [`nba_stats_coaches`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_coaches) | 2026-07-24 |
| [`python/nba_stats_07_draft_creation.py`](python/nba_stats_07_draft_creation.py) | [`draft`](docs/datasets/draft.md) | [`nba_stats_draft`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_draft) | 2026-08-12 |
| [`python/nba_stats_08_schedules_creation.py`](python/nba_stats_08_schedules_creation.py) | [`schedules`](docs/datasets/schedules.md) | [`nba_stats_schedules`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_schedules) | 2026-08-13 |
| [`python/nba_stats_09_player_game_logs_creation.py`](python/nba_stats_09_player_game_logs_creation.py) | [`player_game_logs`](docs/datasets/player_game_logs.md) | [`nba_stats_player_game_logs`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_player_game_logs) | 2026-07-24 |
| [`python/nba_stats_10_pbp_creation.py`](python/nba_stats_10_pbp_creation.py) | [`pbp`](docs/datasets/pbp.md) | [`nba_stats_pbp`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_pbp) | 2026-08-13 |
| [`python/nba_stats_11_game_rosters_creation.py`](python/nba_stats_11_game_rosters_creation.py) | [`game_rosters`](docs/datasets/game_rosters.md) | [`nba_stats_game_rosters`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_game_rosters) | 2026-07-24 |
| [`python/nba_stats_12_officials_creation.py`](python/nba_stats_12_officials_creation.py) | [`officials`](docs/datasets/officials.md) | [`nba_stats_officials`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_officials) | 2026-07-24 |
| [`python/nba_stats_13_player_boxscores_creation.py`](python/nba_stats_13_player_boxscores_creation.py) | [`player_boxscores`](docs/datasets/player_boxscores.md) | [`nba_stats_player_boxscores`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_player_boxscores) | 2026-07-24 |
| [`python/nba_stats_14_team_boxscores_creation.py`](python/nba_stats_14_team_boxscores_creation.py) | [`team_boxscores`](docs/datasets/team_boxscores.md) | [`nba_stats_team_boxscores`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_team_boxscores) | 2026-07-24 |
| [`python/nba_stats_15_shots_creation.py`](python/nba_stats_15_shots_creation.py) | [`shots`](docs/datasets/shots.md) | [`nba_stats_shots`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_shots) | 2026-07-24 |
| [`python/nba_stats_99_schedule_master_creation.py`](python/nba_stats_99_schedule_master_creation.py) | [`schedule_master`](docs/datasets/schedule_master.md) | `nba_stats/nba_stats_schedule_master.parquet` (committed) | — |
| [`python/nba_stats_99_schedule_master_creation.py`](python/nba_stats_99_schedule_master_creation.py) | [`games_in_data_repo`](docs/datasets/games_in_data_repo.md) | `nba_stats/nba_stats_games_in_data_repo.parquet` (committed) | — |
<!-- END GENERATED: datasets -->
