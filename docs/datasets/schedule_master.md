# `schedule_master`

Stage-99 schedule-master artifact (spec D34/D36): every game the schedule knows about — the denominator. The ``in_*`` flag set is derived from the dataset registry, never hand-listed.

| | |
|---|---|
| **Builder** | [`python/nba_stats_99_schedule_master_creation.py`](../../python/nba_stats_99_schedule_master_creation.py) |
| **Committed at** | `nba_stats/nba_stats_schedule_master.parquet` |

## Automation

`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the stage-99 schedule master is restamped at the end of every run.

## Columns

| col_name | type | description |
|---|---|---|
| `PBP` | Boolean | Legacy availability flag carried over from the pre-registry hoopR schedule tree; superseded by in_pbp and kept only because the committed master still carries it. |
| `arena_city` | String | Arena city. |
| `arena_name` | String | Arena the game is played in. |
| `arena_state` | String | Arena state/territory code. |
| `away_team_city` | String | Away team city. |
| `away_team_id` | Int64 | stats.nba.com team id of the away team. |
| `away_team_losses` | Int64 | Away team losses entering/at the game, per the schedule feed. |
| `away_team_name` | String | Away team nickname. |
| `away_team_score` | Int64 | Away final (or current) score. |
| `away_team_seed` | Int64 | Away team playoff seed (playoff games; 0 otherwise). |
| `away_team_slug` | String | Away team URL slug. |
| `away_team_time` | String | Tip time in the away team's local timezone. |
| `away_team_tricode` | String | Away team three-letter code. |
| `away_team_wins` | Int64 | Away team wins entering/at the game, per the schedule feed. |
| `branch_link` | String | NBA app deep link for the game. |
| `day` | String | Day-of-week abbreviation from the schedule feed. |
| `game_code` | String | Schedule game code ("YYYYMMDD/AWYHOM"). |
| `game_date` | String | Game date as the source ships it (calendar date, US Eastern). |
| `game_date_est` | String | Game datetime, US Eastern (date part). |
| `game_date_time_est` | String | Game datetime, US Eastern. |
| `game_date_time_utc` | String | Game datetime, UTC. |
| `game_date_utc` | String | Game date, UTC. |
| `game_id` | String | stats.nba.com game id, zero-padded 10-char string ("0022300001"; the "00" prefix is the NBA league id, so the id must never round-trip through int). |
| `game_label` | String | Special-game label from the schedule feed ("NBA Cup", "Preseason", empty for ordinary games). |
| `game_sequence` | Int64 | Order of the game within its date in the schedule feed. |
| `game_status` | Int64 | Numeric game state (1 scheduled, 2 live, 3 final). |
| `game_status_text` | String | Human-readable game state ("Final", tip time for scheduled games). |
| `game_sub_label` | String | Special-game sub-label ("Championship", group names, usually empty). |
| `game_subtype` | String | Schedule-feed subtype slug for special games (in-season tournament stages). |
| `game_time_est` | String | Game tip time, US Eastern. |
| `game_time_utc` | String | Game tip time, UTC. |
| `home_team_city` | String | Home team city. |
| `home_team_id` | Int64 | stats.nba.com team id of the home team. |
| `home_team_losses` | Int64 | Home team losses entering/at the game, per the schedule feed. |
| `home_team_name` | String | Home team nickname. |
| `home_team_score` | Int64 | Home final (or current) score. |
| `home_team_seed` | Int64 | Home team playoff seed (playoff games; 0 otherwise). |
| `home_team_slug` | String | Home team URL slug. |
| `home_team_time` | String | Tip time in the home team's local timezone. |
| `home_team_tricode` | String | Home team three-letter code. |
| `home_team_wins` | Int64 | Home team wins entering/at the game, per the schedule feed. |
| `if_necessary` | String | "true"/"false": whether a scheduled playoff game is conditional. |
| `in_game_rosters` | Boolean | True when the game is present in the compiled game_rosters release. |
| `in_officials` | Boolean | True when the game is present in the compiled officials release. |
| `in_pbp` | Boolean | True when the game's play-by-play made it into a compiled season release. |
| `in_player_boxscores` | Boolean | True when the game is present in the compiled player_boxscores release. |
| `in_team_boxscores` | Boolean | True when the game is present in the compiled team_boxscores release. |
| `is_neutral` | Boolean | True for neutral-site games. |
| `league_id` | String | stats.nba.com league id ("00" = NBA). |
| `month_num` | Int64 | Schedule-feed month ordinal. |
| `postponed_status` | String | Postponement flag from the schedule feed ("A" = active/none). |
| `season` | String | Season the row belongs to, in one of two forms depending on the artifact. On the reshaped RELEASE assets it is the season's ENDING year as an Int (2024 = the 2023-24 season), matching the asset filename -- the 2026-08-13 republish moved every `nba_stats_*` asset onto END-year names and converted the column with them. On the stage-99 master artifacts committed to `nba_stats/` (`schedule_master`, `games_in_data_repo`) it is the span STRING "1996-97" ... "2025-26", which is what those parquets store and what the schedule builder writes. `draft` and `draft_combine` are an Int in a third sense: the four-digit draft year (2003 = the June 2003 draft, which precedes the 2003-04 season). |
| `season_type_description` | String | Human-readable season type ("Regular Season", "Playoffs", "PlayIn"). |
| `season_type_id` | String | Leading digit of season_id encoding the season type (2 = regular season, 4 = playoffs, 5 = play-in). |
| `series_game_number` | String | Playoff series game number ("Game 5"; empty otherwise). |
| `series_text` | String | Playoff series state text ("BOS leads 3-2"; empty otherwise). |
| `week_name` | String | Schedule-feed week label ("Week 3"). |
| `week_number` | Int64 | Schedule-feed week number (0 for preseason/unassigned). |

## Coverage

_35,361 games across 28 seasons (committed)._
