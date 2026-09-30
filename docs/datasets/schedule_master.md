# `schedule_master`

Stage-99 schedule-master artifact (spec D34/D36): every game the schedule knows about — the denominator. Rows are parsed from the raw store's ``scheduleleaguev2/{season}.json`` (every season type, ``season`` = END year); each ``in_*`` flag is membership in the committed ``nba_stats/{key}/parquet/{stem}_{season}.parquet`` (``master.FLAG_SOURCES``).

| | |
|---|---|
| **Builder** | [`python/nba_stats_99_schedule_master_creation.py`](../../python/nba_stats_99_schedule_master_creation.py) |
| **Committed at** | `nba_stats/nba_stats_schedule_master.parquet` |

## Automation

`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the stage-99 schedule master is restamped at the end of every run.

## Columns

| col_name | type | description |
|---|---|---|
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
| `in_game_rosters` | Boolean | True when the game is in the committed game_rosters season parquet. |
| `in_officials` | Boolean | True when the game is in the committed officials season parquet. |
| `in_pbp` | Boolean | True when the game is in the committed v3 play-by-play (`nba_stats/pbp/parquet/nba_play_by_play_{season}.parquet`). |
| `in_player_boxscores` | Boolean | True when the game is in the committed player_boxscores season parquet. |
| `in_team_boxscores` | Boolean | True when the game is in the committed team_boxscores season parquet. |
| `is_neutral` | Boolean | True for neutral-site games. |
| `league_id` | String | stats.nba.com league id ("00" = NBA). |
| `month_num` | Int64 | Schedule-feed month ordinal. |
| `postponed_status` | String | Postponement flag from the schedule feed ("A" = active/none). |
| `season` | Int64 | Season the row belongs to, as the season's ENDING year Int (2024 = the 2023-24 season), matching the asset filename -- on the reshaped RELEASE assets (the 2026-08-13 republish moved every `nba_stats_*` asset onto END-year names) and on the stage-99 master artifacts committed to `nba_stats/` (`schedule_master`, `games_in_data_repo`; the span STRING "1996-97" they carried until 2026-09-30 is gone). `draft` and `draft_combine` are an Int in a second sense: the four-digit draft year (2003 = the June 2003 draft, which precedes the 2003-04 season). |
| `season_type_description` | String | Human-readable season type ("Regular Season", "Playoffs", "PlayIn"). |
| `season_type_id` | String | Season-type digit: the 3rd character of game_id (and the leading digit of season_id). 1 = preseason, 2 = regular season, 3 = All-Star, 4 = playoffs, 5 = play-in, 6 = NBA Cup final, 9 = international. |
| `series_game_number` | String | Playoff series game number ("Game 5"; empty otherwise). |
| `series_text` | String | Playoff series state text ("BOS leads 3-2"; empty otherwise). |
| `week_name` | String | Schedule-feed week label ("Week 3"). |
| `week_number` | Int64 | Schedule-feed week number (0 for preseason/unassigned). |

## Coverage

_39,359 games across 30 seasons (committed)._

**Every NBA season type is in the master** — preseason (`001`), regular season
(`002`), All-Star (`003`), playoffs (`004`), play-in (`005`) and NBA Cup final
(`006`) — so it counts the full game universe, and `in_pbp` is False wherever
upstream published no play-by-play.

**Preseason play-by-play begins with the 2010-11 season** (END-year 2011): 0 of
119 preseason games in END-year 2010, 119 of 119 in 2011. That era boundary is
1,567 of the 1,602 scheduled games without play-by-play; the rest are All-Star
exhibitions and never-played dates.

**These are upstream absences, not capture gaps — do not re-scrape them.** Each
was re-probed live (2026-08-12/13): stats.nba.com returns a valid `playbyplayv3`
payload with `actions: []` on the same session that returns 500+ actions for
other games. [`docs/nba-v3-coverage.md`](../nba-v3-coverage.md) is the canonical
accounting — per-type counts, the individual game ids, and the `games_no_pbp` vs
`games_failed` distinction.
