# `player_boxscores`

NBA Stats Player Boxscores from hoopR data repository — `boxscoretraditionalv3` (game-level).

| | |
|---|---|
| **Builder** | [`python/nba_stats_13_player_boxscores_creation.py`](../../python/nba_stats_13_player_boxscores_creation.py) |
| **Release tag** | [`nba_stats_player_boxscores`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_player_boxscores) |
| **File stem** | `player_boxscores_{season}.{parquet,csv,rds}` |
| **Seasons built** | 1997–2026 (30 seasons) |
| **Last published** | 2026-08-13 (newest release asset) |
| **Tag created** | 2023-03-30 |
| **Release assets** | 90 |

## Automation

`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the stage-99 schedule master is restamped at the end of every run.

## Columns

| col_name | type | description |
|---|---|---|
| `team_id` | Int64 | stats.nba.com team id (Int64, e.g. 1610612737 = Atlanta Hawks). |
| `team_city` | String | Team city name. |
| `team_name` | String | Team nickname or full name as the source endpoint ships it. |
| `team_tricode` | String | Three-letter team code as the v3 endpoints name it ("ATL"). |
| `team_slug` | String |  |
| `side` | String | Which side of the game the row's team was on: "home" or "away". In `game_matchups`, where a row carries two teams, it is the OFFENSIVE player's team (`off_team_id`) -- the defender is always the other side. |
| `person_id` | Int64 | stats.nba.com person id of the player (or official) the row describes; the same id space as player_id. |
| `first_name` | String |  |
| `family_name` | String |  |
| `name_i` | String |  |
| `player_slug` | String |  |
| `position` | String |  |
| `comment` | String |  |
| `jersey_num` | String |  |
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
| `season` | Int64 | Season the row belongs to, as the season's ENDING year Int (2024 = the 2023-24 season), matching the asset filename -- on the reshaped RELEASE assets (the 2026-08-13 republish moved every `nba_stats_*` asset onto END-year names) and on the stage-99 master artifacts committed to `nba_stats/` (`schedule_master`, `games_in_data_repo`; the span STRING "1996-97" they carried until 2026-09-30 is gone). `draft` and `draft_combine` are an Int in a second sense: the four-digit draft year (2003 = the June 2003 draft, which precedes the 2003-04 season). |
| `season_type_id` | String | Season-type digit: the 3rd character of game_id (and the leading digit of season_id). 1 = preseason, 2 = regular season, 3 = All-Star, 4 = playoffs, 5 = play-in, 6 = NBA Cup final, 9 = international. |

## Coverage

| season | games built | games known |
|---:|---:|---:|
| 1997 | 1,261 | 1,261 |
| 1998 | 1,260 | 1,261 |
| 1999 | 791 | 791 |
| 2000 | 1,264 | 1,264 |
| 2001 | 1,260 | 1,261 |
| 2002 | 1,260 | 1,260 |
| 2003 | 1,277 | 1,277 |
| 2004 | 1,271 | 1,272 |
| 2005 | 1,314 | 1,315 |
| 2006 | 1,319 | 1,322 |
| 2007 | 1,309 | 1,310 |
| 2008 | 1,316 | 1,317 |
| 2009 | 1,315 | 1,317 |
| 2010 | 1,312 | 1,315 |
| 2011 | 1,311 | 1,433 |
| 2012 | 1,074 | 1,107 |
| 2013 | 1,314 | 1,433 |
| 2014 | 1,319 | 1,437 |
| 2015 | 1,311 | 1,431 |
| 2016 | 1,316 | 1,427 |
| 2017 | 1,309 | 1,412 |
| 2018 | 1,312 | 1,392 |
| 2019 | 1,312 | 1,394 |
| 2020 | 1,142 | 1,146 |
| 2021 | 1,165 | 1,221 |
| 2022 | 1,317 | 1,393 |
| 2023 | 1,314 | 1,394 |
| 2024 | 1,312 | 1,396 |
| 2025 | 1,314 | 1,400 |
| 2026 | 1,315 | 1,400 |
