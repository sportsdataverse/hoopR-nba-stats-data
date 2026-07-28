# NBA Stats reshaper port — scope

**Status:** scoping (not yet a task-by-task implementation plan)
**Date:** 2026-07-23
**Author target repo:** `hoopR-nba-stats-data`
**Reference implementation:** `wehoop-wnba-stats-data/python/wnba_data_build/` (the option-1 WNBA reshaper, now with a build+publish CLI)

## Goal

Rebuild the classic `nba_stats_*` release datasets from the unified NBA raw
store (`hoopR-nba-stats-raw`) with Python producers, replacing the old R
pipeline — the same cutover already done for WNBA. `hoopR::load_nba_*()` reads
the `.rds` off those tags, so the port's bar is **schema + stamp parity** with
what the R pipeline publishes today, verified against real release assets.

## Why this is a separate piece, not a wiring task

The two leagues diverged in what got built:

| | WNBA (`wehoop-wnba-stats-data`) | NBA (`hoopR-nba-stats-data`) |
|---|---|---|
| Unified raw store read layer | `raw.py` | ✅ `scrape/raw_store.py` (`read_raw`, `resolve_raw_path`, `season_of`, combined-periods) |
| Reshaper dataset registry | ✅ `datasets.py` (16 datasets → 15 tags) | ❌ none |
| Reshaping builders (resultSets + v3-nested) | ✅ `build.py` | ❌ only a thin modeling `build_season` (rapm/possessions) + the v3-rollup path |
| RDS stamping to the loader's S3 class | ✅ `io.py` (`wehoop_data`) | ❌ none for classic tags |
| Build→publish CLI | ✅ `cli.py` (shipped `1f959fc`) | ✅ but for the v3/modeling tags only, not the classic reshaper tags |
| Classic tags today | Python (cut over) | **still old R pipeline** (release timestamps 2023) |

NBA has the *read* layer and a *different* build path (v3 rollups →
`nba_stats_pbpv3/possessions_v3/lineups_v3`). It has **no** reshaper mapping the
store back to the classic `nba_stats_pbp/schedules/team_boxscores/player_boxscores`
(and the season/roster/standings family). That reshaper subsystem is the port.

## What already exists to build on (do NOT rebuild)

- **`scrape/raw_store.py`** — `read_raw(root, kind, game_id)`,
  `resolve_raw_path` (handles the legacy `{kind}/{game_id}.json` layout AND the
  new shared `{endpoint}/{season}/{game_id}.json`), `period_paths`,
  `season_of(game_id) -> start_year + 1`. This is the NBA equivalent of WNBA's
  `raw.py`; the reshaper reads through it and must not re-implement reading.
- **Raw store breadth** — the NBA store has **64 endpoint dirs** (broader than
  WNBA's 53). Every WNBA-reshaper endpoint is present with data **except
  `drafthistory` (0 files)** — see open question OQ1.

## Raw-store coverage vs the WNBA dataset list (measured)

| WNBA dataset | endpoint | NBA store files | ports 1:1? |
|---|---|---|---|
| standings | leaguestandingsv3 | 62 | yes |
| player_season_stats | leaguedashplayerstats | 868 | yes |
| team_season_stats | leaguedashteamstats | 868 | yes |
| lineups | leaguedashlineups | 868 | yes |
| rosters / coaches | commonteamroster | 879 | yes |
| schedules / player_game_logs | leaguegamelog | 62 | yes |
| pbp | playbyplayv3 | 39,244 | yes |
| game_rosters / officials | boxscoresummaryv2 | 37,853 | yes |
| player_boxscores / team_boxscores | boxscoretraditionalv3 | 39,244 | yes |
| shots | derived from pbp | — | yes |
| **draft** | **drafthistory** | **0** | **no — OQ1** |

15 of 16 WNBA datasets port straight across. Draft is the lone gap.

## The RDS stamp (load-bearing)

hoopR's `make_hoopR_data` (`hoopR/R/utils.R:634`) sets:

```r
class(out) <- c("hoopR_data", "tbl_df", "tbl", "data.table", "data.frame")
attr(out, "hoopR_timestamp") <- timestamp
attr(out, "hoopR_type")      <- type
```

Exactly parallel to WNBA's `wehoop_data`. The NBA `io.py` mirrors WNBA's,
swapping the class vector to `hoopR_data` and the attr keys to
`hoopR_timestamp` / `hoopR_type`. `sportsdataverse._rds.write_rds(df, path,
cls=..., attributes=...)` already does this natively (proven on the WNBA side).

## Divergences from the WNBA port to get right

1. **Season convention.** NBA `season_of` returns **start_year + 1**; the store
   dirs and the classic tags/loaders use the NBA end-year convention (1995-96 =>
   1996). WNBA is a single calendar year. Every `--seasons` value, stem suffix
   (`_{season}`), and `season` column must follow the NBA convention — this is
   the highest-risk source of a silent off-by-one against hoopR's loaders.
2. **Draft source (OQ1).** `drafthistory` has 0 captured files. Either capture
   it in `-raw` or source draft differently. Resolve before claiming draft parity.
3. **Two-store legacy.** ~40k legacy `{kind}/{game_id}.json` files coexist with
   the shared layout. `resolve_raw_path` already abstracts this, so the reshaper
   is unaffected — but the optional legacy-store retirement (separate todo) should
   land *after* parity is proven, not before.
4. **ID dtype discipline.** Per the SDV port rules: fix one dtype per id at the
   boundary, assert `left.schema[k] == right.schema[k]` before every join, never
   a float→Utf8 id cast. `game_id` is zero-padded to 10 in the store.
5. **Parity oracle.** Validate the Python output against the **real R-produced
   release assets** (download the current `nba_stats_*` rds/parquet), not
   synthetic fixtures — column set, dtypes, row counts, and the stamp. This is
   the accept/reject gate for each dataset.

## Proposed shape (mirror WNBA, adapt the five points above)

```
python/nba_data_build/reshape/         # new subpackage; keeps clear of the v3-rollup code
  datasets.py   # Dataset registry -> nba_stats_* tags, hoopR_type strings
  build.py      # resultSets + v3-nested extractors, reading via scrape.raw_store
  io.py         # write_release_formats, hoopR_data stamp
  cli.py        # build -> parquet/rds/csv -> publish (reuse existing publish.py, which is tag-agnostic)
  __main__.py
tests/test_reshape_cli.py              # routing + a real-store parity smoke per dataset
scripts/daily_nba_stats_python_processor.sh   # -s/-e wrapper; venv python by abs path; reads -raw sibling
```

`publish.py` in the NBA repo is already tag/repo-agnostic (WNBA's was ported
from it), so publish is reuse, not new code.

## Not in scope

- The v3-rollup / modeling tags (`nba_stats_pbpv3`, `_possessions_v3`,
  `_lineups_v3`, `_rapm`) — those already have their own Python pipeline.
- Retiring the legacy 40k-file store — separate, post-parity.
- The sdv-orch `data.build_py` cutover for NBA — trivial once the CLI exists
  (mirror the WNBA registry stage), but gated on the port landing.

## Open questions

- **OQ1:** Draft source — capture `drafthistory` in `-raw`, or reshape from a
  different endpoint already in the store?
- **OQ2:** Does the classic NBA family need any dataset WNBA lacks (or vice
  versa)? Cross-check the current `nba_stats_*` tag list against the WNBA 15
  before finalizing the registry.
- **OQ3:** Column parity — are the R-produced classic schemas documented, or is
  the release asset itself the only contract? (Assume the asset is the contract;
  OQ3 just asks whether a cheaper reference exists.)

## Suggested next step

Turn this into a task-by-task implementation plan (writing-plans), one task per
dataset family (season-level resultSets → game-level → derived shots → draft),
each ending in a parity assertion against the live release asset. Resolve OQ1
first, since draft is the only dataset without a clear raw source.
```
