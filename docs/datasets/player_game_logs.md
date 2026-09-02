# `player_game_logs`

NBA Stats Player Game Logs from hoopR data repository — `leaguegamelog` (season-level).

| | |
|---|---|
| **Builder** | [`python/nba_stats_09_player_game_logs_creation.py`](../../python/nba_stats_09_player_game_logs_creation.py) |
| **Release tag** | [`nba_stats_player_game_logs`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_player_game_logs) |
| **File stem** | `player_game_logs_{season}.{parquet,csv,rds}` |
| **Seasons built** | — |
| **Last published** | 2026-08-13 (newest release asset) |
| **Tag created** | 2026-07-24 |
| **Release assets** | 90 |

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
| `season` | Int64 | Season the row belongs to, in one of two forms depending on the artifact. On the reshaped RELEASE assets it is the season's ENDING year as an Int (2024 = the 2023-24 season), matching the asset filename -- the 2026-08-13 republish moved every `nba_stats_*` asset onto END-year names and converted the column with them. On the stage-99 master artifacts committed to `nba_stats/` (`schedule_master`, `games_in_data_repo`) it is the span STRING "1996-97" ... "2025-26", which is what those parquets store and what the schedule builder writes. `draft` and `draft_combine` are an Int in a third sense: the four-digit draft year (2003 = the June 2003 draft, which precedes the 2003-04 season). |
| `season_type` | String | Season type the capture was made under ("Regular Season", "Playoffs", ...). |

## Coverage

_Coverage is tracked per release asset on [`nba_stats_player_game_logs`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_player_game_logs)._
