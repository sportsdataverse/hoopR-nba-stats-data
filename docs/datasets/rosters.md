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
| `season` | Int64 | Season the row belongs to. On the reshaped release assets it is the season's ENDING year as an integer, matching the asset filename (2024 = the 2023-24 season) -- the 2026-08-13 republish moved every `nba_stats_*` asset onto END-year names and the column was converted with them. The span form ("2023-24") survives only where a payload carries its own season column. `draft` and `draft_combine` are the exception in the other direction: their integer is the four-digit draft year (2003 = the June 2003 draft, which precedes the 2003-04 season). |
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
