# `injury_report`

NBA Stats Official Injury Report from hoopR data repository — `derived` (derived-level).

The NBA's official injury report -- every published version, one row per listing. The league re-publishes the report through the day (three times a day through 2021-10-14, hourly until 2025-12-21, every 15 minutes since), so a player appears once per version he is listed in, and `report_datetime` (US/Eastern, naive) tells the versions apart. `current_status` is the printed status (Available, Probable, Questionable, Doubtful, Out); a team that had not filed by a version is one row with a null `report_player_name` and `reason` "NOT YET SUBMITTED". `game_id` and `team_id` are joined from the schedule (`game_id` is null for a game postponed off its printed date, or a playoff game that was not needed); `person_id` is matched by name on the team from the season's player boxscores, then its rosters (`match_method` exact / family / league / roster, null when unmatched). Span 2018-12-17 (the archive's first report) to present; seasons are END years (2019 = 2018-19).

| | |
|---|---|
| **Builder** | [`python/nba_stats_19_injury_report_creation.py`](../../python/nba_stats_19_injury_report_creation.py) |
| **Release tag** | [`nba_stats_injury_report`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_injury_report) |
| **File stem** | `injury_report_{season}.{parquet,csv,rds}` |
| **Seasons built** | — |
| **Last published** | — (newest release asset) |
| **Tag created** | — |
| **Release assets** | — |

## Automation

`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the stage-99 schedule master is restamped at the end of every run.

## Columns

| col_name | type | description |
|---|---|---|
| `season` | Int64 | Season the row belongs to, as the season's ENDING year Int (2024 = the 2023-24 season), matching the asset filename -- on the reshaped RELEASE assets (the 2026-08-13 republish moved every `nba_stats_*` asset onto END-year names) and on the stage-99 master artifacts committed to `nba_stats/` (`schedule_master`, `games_in_data_repo`; the span STRING "1996-97" they carried until 2026-09-30 is gone). `draft` and `draft_combine` are an Int in a second sense: the four-digit draft year (2003 = the June 2003 draft, which precedes the 2003-04 season). |
| `report_datetime` | Datetime(time_unit='us', time_zone=None) | Publish time of the injury-report version the row comes from (US Eastern, naive). The league re-publishes the report through the day, so one listing repeats once per version. |
| `game_date` | Date | Game date as the source ships it (calendar date, US Eastern). |
| `game_time` | String | Tip time as the injury report prints it ("07:30 (ET)", no AM/PM). |
| `report_matchup` | String | Game as the injury report prints it, away@home tricodes ("CLE@ATL"). |
| `away_team_abbr` | String | Away team tricode as the injury report prints it ("CLE"). |
| `home_team_abbr` | String | Home team tricode as the injury report prints it ("ATL"). |
| `team` | String | Team the listing belongs to, full name as the injury report prints it ("Cleveland Cavaliers"). |
| `report_player_name` | String | Player as the injury report prints it, "Last, First" ("James, LeBron"); null on a team's "NOT YET SUBMITTED" row. |
| `current_status` | String | Listed status in that version: Available, Probable, Questionable, Doubtful or Out (null on a "NOT YET SUBMITTED" row). |
| `reason` | String | Reason as printed ("Injury/Illness - Left Ankle; Sprain", "G League - Two-Way", "NOT YET SUBMITTED" for a team that had not filed). |
| `category` | String | Category column of the early report format; last printed 2019-11-14, null after. |
| `previous_status` | String | Previous Status column of the early report format (the player's status in the prior version); last printed 2019-12-17, null after. |
| `game_id` | String | stats.nba.com game id, zero-padded 10-char string ("0022300001"; the "00" prefix is the NBA league id, so the id must never round-trip through int). |
| `team_id` | Int64 | stats.nba.com team id (e.g. 1610612737 = Atlanta Hawks). |
| `person_id` | Int64 | stats.nba.com person id of the player (or official) the row describes; the same id space as player_id. |
| `match_method` | String | How person_id was matched to the printed name: exact (full name on the team that season), family (family name + first initial, unique on the team), league (name unique league-wide that season), roster (name on the team's roster, which also lists players who have not played), or null (unmatched). |

## Coverage

_Coverage is tracked per release asset on [`nba_stats_injury_report`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_injury_report)._
