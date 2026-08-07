# `schedules`

NBA Stats Schedule from hoopR data repository — `leaguegamelog` (season-level).

| | |
|---|---|
| **Builder** | [`python/nba_stats_08_schedules_creation.py`](../../python/nba_stats_08_schedules_creation.py) |
| **Release tag** | [`nba_stats_schedules`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_schedules) |
| **File stem** | `nba_stats_schedule_{season}.{parquet,csv,rds}` |
| **Seasons built** | — |
| **Last published** | 2026-07-24 (newest release asset) |
| **Tag created** | 2023-03-30 |
| **Release assets** | 97 |

## Automation

`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the stage-99 schedule master is restamped at the end of every run.

## Columns

| col_name | type | description |
|---|---|---|
| `season_id` | String | stats.nba.com composite season id: season-type digit + start year ("22023" = 2023-24 regular season). |
| `team_id` | Int64 | stats.nba.com team id (Int64, e.g. 1610612737 = Atlanta Hawks). |
| `team_abbreviation` | String | Three-letter team code ("ATL"). |
| `team_name` | String | Team nickname or full name as the source endpoint ships it. |
| `game_id` | String | stats.nba.com game id, zero-padded 10-char string ("0022300001"; the "00" prefix is the NBA league id, so the id must never round-trip through int). |
| `game_date` | String | Game date as the source ships it (calendar date, US Eastern). |
| `matchup` | String | Matchup string from the log ("ATL @ BOS" away, "ATL vs. BOS" home). |
| `wl` | String | Result from the row team's perspective: "W" or "L". |
| `min` | Int64 | Team (or player) minutes in the log row. |
| `fgm` | Int64 | Field goals made. |
| `fga` | Int64 | Field goals attempted. |
| `fg_pct` | Float64 | Field-goal percentage (0-1). |
| `fg3m` | Int64 | Three-point field goals made. |
| `fg3a` | Int64 | Three-point field goals attempted. |
| `fg3_pct` | Float64 | Three-point percentage (0-1). |
| `ftm` | Int64 | Free throws made. |
| `fta` | Int64 | Free throws attempted. |
| `ft_pct` | Float64 | Free-throw percentage (0-1). |
| `oreb` | Int64 | Offensive rebounds. |
| `dreb` | Int64 | Defensive rebounds. |
| `reb` | Int64 | Total rebounds. |
| `ast` | Int64 | Assists. |
| `stl` | Int64 | Steals. |
| `blk` | Int64 | Blocks. |
| `tov` | Int64 | Turnovers. |
| `pf` | Int64 | Personal fouls. |
| `pts` | Int64 | Points. |
| `plus_minus` | Int64 | Point differential while on the floor (player rows) or final margin (team rows). |
| `video_available` | Int64 | 1 when the feed links video for the action/game row. |
| `season` | Int64 | Season the row belongs to. Stats-API span form for NBA ("2023-24") in the released season assets; the schedule master carries the same span form. |
| `season_type` | String | Season type the capture was made under ("Regular Season", "Playoffs", ...). |

## Coverage

_Coverage is tracked per release asset on [`nba_stats_schedules`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_schedules)._
