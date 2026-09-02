# `draft`

NBA Stats Draft History from hoopR data repository — `drafthistory` (season-level).

| | |
|---|---|
| **Builder** | [`python/nba_stats_07_draft_creation.py`](../../python/nba_stats_07_draft_creation.py) |
| **Release tag** | [`nba_stats_draft`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_draft) |
| **File stem** | `draft_{season}.{parquet,csv,rds}` |
| **Seasons built** | — |
| **Last published** | 2026-08-13 (newest release asset) |
| **Tag created** | 2026-08-12 |
| **Release assets** | 90 |

## Automation

`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the stage-99 schedule master is restamped at the end of every run.

## Columns

| col_name | type | description |
|---|---|---|
| `person_id` | Int64 | stats.nba.com person id of the player (or official) the row describes; the same id space as player_id. |
| `player_name` | String | Player display name as the stats API ships it ("LeBron James"). |
| `season` | Int64 | Season the row belongs to. On the reshaped release assets it is the season's ENDING year as an integer, matching the asset filename (2024 = the 2023-24 season) -- the 2026-08-13 republish moved every `nba_stats_*` asset onto END-year names and the column was converted with them. The span form ("2023-24") survives only where a payload carries its own season column. `draft` and `draft_combine` are the exception in the other direction: their integer is the four-digit draft year (2003 = the June 2003 draft, which precedes the 2003-04 season). |
| `round_number` | Int64 | Draft round the pick was made in (1 or 2 across the published 1996-2025 range; earlier drafts ran to more rounds). |
| `round_pick` | Int64 | Pick number WITHIN the round (the 5th pick of round 2 is round_pick 5, not 35). Use overall_pick for draft-wide order. |
| `overall_pick` | Int64 | Pick number across the whole draft, 1 = first overall. |
| `draft_type` | String | How the player entered the league. "Draft" for every pick in the published range; the value exists to distinguish historical dispersal, expansion and territorial drafts in older seasons. |
| `team_id` | Int64 | stats.nba.com team id (Int64, e.g. 1610612737 = Atlanta Hawks). |
| `team_city` | String | Team city name. |
| `team_name` | String | Team nickname or full name as the source endpoint ships it. |
| `team_abbreviation` | String | Three-letter team code ("ATL"). |
| `organization` | String | School, club or national team the player came from ("Syracuse", "KK Vrsac (Serbia)"). Populated for ~99.9% of NBA picks; the WNBA twin ships it empty. |
| `organization_type` | String | Category of `organization`: "College/University" (1,395 of the 1,773 picks 1996-2025), "Other Team/Club" (333; mostly international clubs), "High School" (43) or empty (2 -- Thon Maker 2016, Mitchell Robinson 2018, both of whom also ship an empty `organization`). Note "High School" is not confined to the pre-2006 prep-to-pro era: it is whatever the API last recorded, and it recurs in 2015-2020 for picks with no college of record. |
| `player_profile_flag` | Int64 | 1 when stats.nba.com hosts a player profile for the pick, 0 when it does not (166 of 1,773 picks 1996-2025). Largely tracks whether the pick ever reached the NBA, but it is a profile-existence flag rather than a games-played one, so it should not be read as a career indicator on its own. |

## Coverage

_Coverage is tracked per release asset on [`nba_stats_draft`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_draft)._
