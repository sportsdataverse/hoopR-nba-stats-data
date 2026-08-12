# `game_rosters`

NBA Stats Game Rosters from hoopR data repository — `boxscoresummaryv2` (game-level).

| | |
|---|---|
| **Builder** | [`python/nba_stats_11_game_rosters_creation.py`](../../python/nba_stats_11_game_rosters_creation.py) |
| **Release tag** | [`nba_stats_game_rosters`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_game_rosters) |
| **File stem** | `game_rosters_{season}.{parquet,csv,rds}` |
| **Seasons built** | 1996-97–2025-26 (28 seasons, non-contiguous) |
| **Last published** | 2026-07-24 (newest release asset) |
| **Tag created** | 2026-07-24 |
| **Release assets** | 90 |

## Automation

`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the stage-99 schedule master is restamped at the end of every run.

## Columns

| col_name | type | description |
|---|---|---|
| `player_id` | Int64 | stats.nba.com person id of the player (Int64); joins rosters, boxscores, game logs and pbp (`person_id`). |
| `first_name` | String |  |
| `last_name` | String |  |
| `jersey_num` | String |  |
| `team_id` | Int64 | stats.nba.com team id (Int64, e.g. 1610612737 = Atlanta Hawks). |
| `team_city` | String | Team city name. |
| `team_name` | String | Team nickname or full name as the source endpoint ships it. |
| `team_abbreviation` | String | Three-letter team code ("ATL"). |
| `season` | Int64 | Season the row belongs to. Stats-API span form for NBA ("2023-24") in the released season assets; the schedule master carries the same span form. `draft` is the exception: it carries the four-digit draft year as an integer (2003 = the June 2003 draft, which precedes the 2003-04 season). |
| `game_id` | String | stats.nba.com game id, zero-padded 10-char string ("0022300001"; the "00" prefix is the NBA league id, so the id must never round-trip through int). |

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
| 2025-26 | 1,308 | 1,400 |
