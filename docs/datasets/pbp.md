# `pbp`

NBA Stats Play-by-Play from hoopR data repository — `playbyplayv3` (game-level).

| | |
|---|---|
| **Builder** | [`python/nba_stats_10_pbp_creation.py`](../../python/nba_stats_10_pbp_creation.py) |
| **Release tag** | [`nba_stats_pbp`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_pbp) |
| **File stem** | `play_by_play_{season}.{parquet,csv,rds}` |
| **Seasons built** | 1996-97–2025-26 (28 seasons, non-contiguous) |
| **Last published** | 2026-08-13 (newest release asset) |
| **Tag created** | 2023-03-30 |
| **Release assets** | 181 |

## Automation

`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the stage-99 schedule master is restamped at the end of every run.

## Columns

| col_name | type | description |
|---|---|---|
| `action_number` | Int64 | Ordinal of the action within the game as numbered by the stats feed; monotone but not gapless (video-only actions are skipped). |
| `clock` | String | Game clock at the action in ISO-8601 duration form ("PT11M32.00S"). |
| `period` | Int64 | Period number (1-4; 5+ = overtime). |
| `team_id` | Int64 | stats.nba.com team id (Int64, e.g. 1610612737 = Atlanta Hawks). |
| `team_tricode` | String | Three-letter team code as the v3 endpoints name it ("ATL"). |
| `person_id` | Int64 | stats.nba.com person id of the player (or official) the row describes; the same id space as player_id. |
| `player_name` | String | Player display name as the stats API ships it ("LeBron James"). |
| `player_name_i` | String | Abbreviated player name ("L. James"). |
| `x_legacy` | Int64 | Shot x-coordinate in the legacy stats.nba.com coordinate frame (tenths of feet from the basket centerline; null for non-shots). |
| `y_legacy` | Int64 | Shot y-coordinate in the legacy coordinate frame (tenths of feet from the baseline; null for non-shots). |
| `shot_distance` | Int64 | Shot distance in feet (0 for non-shots). |
| `shot_result` | String | "Made" / "Missed" for shot actions; empty otherwise. |
| `is_field_goal` | Int64 | 1 when the action is a field-goal attempt, else 0. |
| `score_home` | String | Home score after the action (string; carried forward between scores). |
| `score_away` | String | Away score after the action (string; carried forward between scores). |
| `points_total` | Int64 | Points the acting team has scored through this action. |
| `location` | String | Which side the acting team is on: "h" (home) or "v" (visitor). |
| `description` | String | Human-readable action narrative from the feed. |
| `action_type` | String | Action family ("Made Shot", "Rebound", "Turnover", "Foul", ...). |
| `sub_type` | String | Action detail within the family ("Jump Shot", "Offensive", ...). |
| `video_available` | Int64 | 1 when the feed links video for the action/game row. |
| `shot_value` | Int64 | Point value of a shot attempt (2 or 3; 1 for free throws, 0 for non-shots). |
| `action_id` | Int64 | Feed-internal id of the action row. |
| `game_id` | String | stats.nba.com game id, zero-padded 10-char string ("0022300001"; the "00" prefix is the NBA league id, so the id must never round-trip through int). |
| `season` | Int64 | Season the row belongs to. On the reshaped release assets it is the season's ENDING year as an integer, matching the asset filename (2024 = the 2023-24 season) -- the 2026-08-13 republish moved every `nba_stats_*` asset onto END-year names and the column was converted with them. The span form ("2023-24") survives only where a payload carries its own season column. `draft` and `draft_combine` are the exception in the other direction: their integer is the four-digit draft year (2003 = the June 2003 draft, which precedes the 2003-04 season). |

## Coverage

| season | games built | games known |
|---:|---:|---:|
| 1996-97 | 1,261 | 1,261 |
| 1997-98 | 1,260 | 1,260 |
| 1998-99 | 791 | 791 |
| 1999-00 | 1,264 | 1,264 |
| 2000-01 | 1,260 | 1,260 |
| 2001-02 | 1,260 | 1,260 |
| 2002-03 | 1,277 | 1,277 |
| 2003-04 | 1,271 | 1,271 |
| 2004-05 | 1,314 | 1,314 |
| 2005-06 | 1,319 | 1,319 |
| 2006-07 | 1,309 | 1,309 |
| 2007-08 | 1,316 | 1,316 |
| 2008-09 | 1,315 | 1,315 |
| 2009-10 | 1,312 | 1,312 |
| 2010-11 | 1,311 | 1,311 |
| 2011-12 | 1,074 | 1,074 |
| 2012-13 | 1,314 | 1,314 |
| 2013-14 | 1,319 | 1,319 |
| 2014-15 | 1,311 | 1,311 |
| 2015-16 | 1,316 | 1,316 |
| 2016-17 | 1,309 | 1,309 |
| 2017-18 | 1,312 | 1,312 |
| 2018-19 | 1,312 | 1,312 |
| 2019-20 | 1,142 | 1,142 |
| 2020-21 | 1,165 | 1,165 |
| 2021-22 | 1,317 | 1,317 |
| 2022-23 | 1,230 | 1,230 |
| 2025-26 | 1,400 | 1,400 |

**Every NBA season type is published** — preseason (`001`), regular season
(`002`), All-Star (`003`), playoffs (`004`), play-in (`005`) and NBA Cup final
(`006`) — so `games known` counts the full game universe, and a season's
`games built` is below it wherever upstream published no play-by-play.

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
