# `rosters`

NBA Stats Rosters from hoopR data repository — `commonteamroster` (season-level).

| | |
|---|---|
| **Builder** | [`python/nba_stats_05_rosters_creation.py`](../../python/nba_stats_05_rosters_creation.py) |
| **Release tag** | [`nba_stats_rosters`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_rosters) |
| **File stem** | `rosters_{season}.{parquet,csv,rds}` |
| **Seasons built** | — |
| **Last published** | 2026-08-13 (newest release asset) |
| **Tag created** | 2026-07-24 |
| **Release assets** | 90 |

## Automation

`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the stage-99 schedule master is restamped at the end of every run.

## Columns

| col_name | type | description |
|---|---|---|
| `team_id` | Int64 | stats.nba.com team id (Int64, e.g. 1610612737 = Atlanta Hawks). |
| `season` | Int64 | Season the row belongs to, in one of two forms depending on the artifact. On the reshaped RELEASE assets it is the season's ENDING year as an Int (2024 = the 2023-24 season), matching the asset filename -- the 2026-08-13 republish moved every `nba_stats_*` asset onto END-year names and converted the column with them. On the stage-99 master artifacts committed to `nba_stats/` (`schedule_master`, `games_in_data_repo`) it is the span STRING "1996-97" ... "2025-26", which is what those parquets store and what the schedule builder writes. `draft` and `draft_combine` are an Int in a third sense: the four-digit draft year (2003 = the June 2003 draft, which precedes the 2003-04 season). |
| `league_id` | String | stats.nba.com league id ("00" = NBA). |
| `player` | String |  |
| `nickname` | String |  |
| `player_slug` | String |  |
| `num` | String |  |
| `position` | String |  |
| `height` | String |  |
| `weight` | String |  |
| `birth_date` | String |  |
| `age` | Float64 |  |
| `exp` | String |  |
| `school` | String |  |
| `player_id` | Int64 | stats.nba.com person id of the player (Int64); joins rosters, boxscores, game logs and pbp (`person_id`). |
| `how_acquired` | String |  |
| `season_type` | String | Season type the capture was made under ("Regular Season", "Playoffs", ...). |

## Coverage

_Coverage is tracked per release asset on [`nba_stats_rosters`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_rosters)._
