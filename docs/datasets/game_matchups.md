# `game_matchups`

NBA Stats Game Matchups from hoopR data repository — `boxscorematchupsv3` (game-level).

| | |
|---|---|
| **Builder** | [`python/nba_stats_16_game_matchups_creation.py`](../../python/nba_stats_16_game_matchups_creation.py) |
| **Release tag** | [`nba_stats_game_matchups`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_game_matchups) |
| **File stem** | `game_matchups_{season}.{parquet,csv,rds}` |
| **Seasons built** | — |
| **Last published** | — (newest release asset) |
| **Tag created** | — |
| **Release assets** | — |

## Automation

`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the stage-99 schedule master is restamped at the end of every run.

## Columns

| col_name | type | description |
|---|---|---|
| `off_team_id` | Int64 | Team id of the offensive player. Taken from the payload's team block. |
| `off_team_city` | String | City/market of the offensive player's team ("Indiana"). |
| `off_team_name` | String | Nickname of the offensive player's team ("Pacers") -- pair with `off_team_city` for the full club name. |
| `off_team_tricode` | String | Three-letter abbreviation of the offensive player's team ("IND"). |
| `off_team_slug` | String | URL slug of the offensive player's team ("pacers"). |
| `def_team_id` | Int64 | Team id of the defender, read from the game envelope's homeTeamId/awayTeamId rather than the nested team object, which is 0 on uncovered captures. |
| `side` | String | Which side of the game the OFFENSIVE player's team was on: "home" or "away". |
| `off_person_id` | Int64 | stats.nba.com person id of the offensive player -- the one being guarded. |
| `off_first_name` | String | First name of the offensive player. |
| `off_family_name` | String | Family name of the offensive player. |
| `off_name_i` | String | Offensive player's abbreviated display name ("B. Mathurin"). |
| `off_player_slug` | String | URL slug of the offensive player ("bennedict-mathurin"). |
| `off_position` | String | Starting position of the offensive player as the payload reports it; empty for players who did not start. |
| `off_comment` | String | Availability note on the offensive player (DNP reason); empty when they played. |
| `off_jersey_num` | String | Jersey number of the offensive player, as a string (it can carry a leading zero, e.g. "00"). |
| `def_person_id` | Int64 | stats.nba.com person id of the defender guarding the offensive player. |
| `def_first_name` | String | First name of the defender. |
| `def_family_name` | String | Family name of the defender. |
| `def_name_i` | String | Defender's abbreviated display name ("J. Allen"). |
| `def_player_slug` | String | URL slug of the defender ("jarrett-allen"). |
| `def_jersey_num` | String | Jersey number of the defender, as a string (it can carry a leading zero). |
| `matchup_minutes` | String | Time the pair were matched up, as the payload's MM:SS string; use `matchup_minutes_sort` for arithmetic. |
| `matchup_minutes_sort` | Float64 | The same matchup time in seconds, as a float -- the sortable/summable form. |
| `partial_possessions` | Float64 | Possessions credited to the matchup. Fractional because a possession is split across every defender who guarded the ball-handler during it, which is why matchup counting stats do not sum exactly to a player's game totals. |
| `percentage_defender_total_time` | Float64 | Share of the defender's floor time spent guarding this offensive player. |
| `percentage_offensive_total_time` | Float64 | Share of the offensive player's floor time spent guarded by this defender. |
| `percentage_total_time_both_on` | Float64 | Share of the time both players were on the floor together that they were matched up. |
| `switches_on` | Int64 | Times the defense switched this defender onto the offensive player. |
| `player_points` | Int64 | Points the offensive player scored while guarded by this defender. |
| `team_points` | Int64 | Points the offensive player's team scored while this matchup was on. |
| `matchup_assists` | Int64 | Assists by the offensive player while guarded by this defender. |
| `matchup_potential_assists` | Int64 | Passes by the offensive player that would have been assists had the shot fallen, while guarded by this defender. |
| `matchup_turnovers` | Int64 | Turnovers by the offensive player while guarded by this defender. |
| `matchup_blocks` | Int64 | Shots by the offensive player blocked by this defender. |
| `matchup_field_goals_made` | Int64 | Field goals made by the offensive player against this defender. |
| `matchup_field_goals_attempted` | Int64 | Field goals attempted by the offensive player against this defender. |
| `matchup_field_goals_percentage` | Float64 | Field-goal percentage of the offensive player against this defender. |
| `matchup_three_pointers_made` | Int64 | Three-pointers made by the offensive player against this defender. |
| `matchup_three_pointers_attempted` | Int64 | Three-pointers attempted by the offensive player against this defender. |
| `matchup_three_pointers_percentage` | Float64 | Three-point percentage of the offensive player against this defender. |
| `help_blocks` | Int64 | Blocks by this defender on the offensive player when helping off another assignment rather than as the primary defender. |
| `help_field_goals_made` | Int64 | Field goals the offensive player made against this defender in help defense. |
| `help_field_goals_attempted` | Int64 | Field goals the offensive player attempted against this defender in help defense. |
| `help_field_goals_percentage` | Float64 | Field-goal percentage allowed by this defender in help defense. |
| `matchup_free_throws_made` | Int64 | Free throws made by the offensive player on trips drawn against this defender. |
| `matchup_free_throws_attempted` | Int64 | Free throws attempted by the offensive player on trips drawn against this defender. |
| `shooting_fouls` | Int64 | Shooting fouls committed by this defender on the offensive player. |
| `game_id` | String | stats.nba.com game id, zero-padded 10-char string ("0022300001"; the "00" prefix is the NBA league id, so the id must never round-trip through int). |
| `season` | Int64 | Season the row belongs to. On the reshaped release assets it is the season's ENDING year as an integer, matching the asset filename (2024 = the 2023-24 season) -- the 2026-08-13 republish moved every `nba_stats_*` asset onto END-year names and the column was converted with them. The span form ("2023-24") survives only where a payload carries its own season column. `draft` and `draft_combine` are the exception in the other direction: their integer is the four-digit draft year (2003 = the June 2003 draft, which precedes the 2003-04 season). |

## Coverage

_Coverage is tracked per release asset on [`nba_stats_game_matchups`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_game_matchups)._
