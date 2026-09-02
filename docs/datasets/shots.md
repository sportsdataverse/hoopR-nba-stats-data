# `shots`

NBA Stats Shots from hoopR data repository — `derived` (derived-level).

| | |
|---|---|
| **Builder** | [`python/nba_stats_15_shots_creation.py`](../../python/nba_stats_15_shots_creation.py) |
| **Release tag** | [`nba_stats_shots`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_shots) |
| **File stem** | `shots_{season}.{parquet,csv,rds}` |
| **Seasons built** | — |
| **Last published** | 2026-08-13 (newest release asset) |
| **Tag created** | 2026-07-24 |
| **Release assets** | 90 |

## Automation

`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the stage-99 schedule master is restamped at the end of every run.

## Columns

| col_name | type | description |
|---|---|---|
| `game_id` | String | stats.nba.com game id, zero-padded 10-char string ("0022300001"; the "00" prefix is the NBA league id, so the id must never round-trip through int). |
| `season` | Int64 | Season the row belongs to, in one of two forms depending on the artifact. On the reshaped RELEASE assets it is the season's ENDING year as an Int (2024 = the 2023-24 season), matching the asset filename -- the 2026-08-13 republish moved every `nba_stats_*` asset onto END-year names and converted the column with them. On the stage-99 master artifacts committed to `nba_stats/` (`schedule_master`, `games_in_data_repo`) it is the span STRING "1996-97" ... "2025-26", which is what those parquets store and what the schedule builder writes. `draft` and `draft_combine` are an Int in a third sense: the four-digit draft year (2003 = the June 2003 draft, which precedes the 2003-04 season). |
| `period` | Int64 | Period number (1-4; 5+ = overtime). |
| `clock` | String | Game clock at the action in ISO-8601 duration form ("PT11M32.00S"). |
| `team_id` | Int64 | stats.nba.com team id (Int64, e.g. 1610612737 = Atlanta Hawks). |
| `team_tricode` | String | Three-letter team code as the v3 endpoints name it ("ATL"). |
| `person_id` | Int64 | stats.nba.com person id of the player (or official) the row describes; the same id space as player_id. |
| `player_name` | String | Player display name as the stats API ships it ("LeBron James"). |
| `action_type` | String | Action family ("Made Shot", "Rebound", "Turnover", "Foul", ...). |
| `sub_type` | String | Action detail within the family ("Jump Shot", "Offensive", ...). |
| `shot_result` | String | "Made" / "Missed" for shot actions; empty otherwise. |
| `shot_value` | Int64 | Point value of a shot attempt (2 or 3; 1 for free throws, 0 for non-shots). |
| `shot_distance` | Int64 | Shot distance in feet (0 for non-shots). |
| `x_legacy` | Int64 | Shot x-coordinate in the legacy stats.nba.com coordinate frame (tenths of feet from the basket centerline; null for non-shots). |
| `y_legacy` | Int64 | Shot y-coordinate in the legacy coordinate frame (tenths of feet from the baseline; null for non-shots). |
| `description` | String | Human-readable action narrative from the feed. |
| `score_home` | String | Home score after the action (string; carried forward between scores). |
| `score_away` | String | Away score after the action (string; carried forward between scores). |

## Coverage

_Coverage is tracked per release asset on [`nba_stats_shots`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_shots)._
