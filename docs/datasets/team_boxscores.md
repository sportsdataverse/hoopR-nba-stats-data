# `team_boxscores`

NBA Stats Team Boxscores from hoopR data repository — `boxscoretraditionalv3` (game-level).

| | |
|---|---|
| **Builder** | [`python/nba_stats_14_team_boxscores_creation.py`](../../python/nba_stats_14_team_boxscores_creation.py) |
| **Release tag** | [`nba_stats_team_boxscores`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_team_boxscores) |
| **File stem** | `team_boxscores_{season}.{parquet,csv,rds}` |
| **Seasons built** | 1996-97–2025-26 (28 seasons, non-contiguous) |
| **Last published** | 2026-08-13 (newest release asset) |
| **Tag created** | 2023-03-30 |
| **Release assets** | 90 |

## Automation

`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the stage-99 schedule master is restamped at the end of every run.

## Columns

| col_name | type | description |
|---|---|---|
| `team_id` | Int64 | stats.nba.com team id (Int64, e.g. 1610612737 = Atlanta Hawks). |
| `team_name` | String | Team nickname or full name as the source endpoint ships it. |
| `team_tricode` | String | Three-letter team code as the v3 endpoints name it ("ATL"). |
| `side` | String | Which side of the game the OFFENSIVE player's team was on: "home" or "away". |
| `minutes` | String |  |
| `field_goals_made` | Int64 |  |
| `field_goals_attempted` | Int64 |  |
| `field_goals_percentage` | Float64 |  |
| `three_pointers_made` | Int64 |  |
| `three_pointers_attempted` | Int64 |  |
| `three_pointers_percentage` | Float64 |  |
| `free_throws_made` | Int64 |  |
| `free_throws_attempted` | Int64 |  |
| `free_throws_percentage` | Float64 |  |
| `rebounds_offensive` | Int64 |  |
| `rebounds_defensive` | Int64 |  |
| `rebounds_total` | Int64 |  |
| `assists` | Int64 |  |
| `steals` | Int64 |  |
| `blocks` | Int64 |  |
| `turnovers` | Int64 |  |
| `fouls_personal` | Int64 |  |
| `points` | Int64 |  |
| `plus_minus_points` | Float64 |  |
| `game_id` | String | stats.nba.com game id, zero-padded 10-char string ("0022300001"; the "00" prefix is the NBA league id, so the id must never round-trip through int). |
| `season` | Int64 | Season the row belongs to. On the reshaped release assets it is the season's ENDING year as an integer, matching the asset filename (2024 = the 2023-24 season) -- the 2026-08-13 republish moved every `nba_stats_*` asset onto END-year names and the column was converted with them. The span form ("2023-24") survives only where a payload carries its own season column. `draft` and `draft_combine` are the exception in the other direction: their integer is the four-digit draft year (2003 = the June 2003 draft, which precedes the 2003-04 season). |

## Coverage

| season | games built | games known |
|---:|---:|---:|
| 1996-97 | 1,261 | 1,261 |
| 1997-98 | 1,260 | 1,260 |
| 1998-99 | 791 | 791 |
| 1999-00 | 1,264 | 1,264 |
| 2000-01 | 1,260 | 1,260 |
| 2001-02 | 1,260 | 1,260 |
| 2002-03 | 1,277 | 1,277 |
| 2003-04 | 1,271 | 1,271 |
| 2004-05 | 1,314 | 1,314 |
| 2005-06 | 1,319 | 1,319 |
| 2006-07 | 1,309 | 1,309 |
| 2007-08 | 1,316 | 1,316 |
| 2008-09 | 1,315 | 1,315 |
| 2009-10 | 1,312 | 1,312 |
| 2010-11 | 1,311 | 1,311 |
| 2011-12 | 1,074 | 1,074 |
| 2012-13 | 1,314 | 1,314 |
| 2013-14 | 1,319 | 1,319 |
| 2014-15 | 1,311 | 1,311 |
| 2015-16 | 1,316 | 1,316 |
| 2016-17 | 1,309 | 1,309 |
| 2017-18 | 1,312 | 1,312 |
| 2018-19 | 1,312 | 1,312 |
| 2019-20 | 1,142 | 1,142 |
| 2020-21 | 1,165 | 1,165 |
| 2021-22 | 1,317 | 1,317 |
| 2022-23 | 1,230 | 1,230 |
| 2025-26 | 1,400 | 1,400 |
