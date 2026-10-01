# `rolling_windows`

NBA Stats Rolling Shooting Windows from hoopR data repository — `derived` (derived-level).

Rolling shooting form -- every shooter's last N field-goal attempts (`fga`, metric `fg_pct`) and last N three-point attempts (`fg3a`, metric `fg3_pct`), N = 50 and 200, computed by `sportsdataverse.rolling_windows` from the committed `nba_stats_shots`. One row per (season, player, window_unit, window_n) for every player with an attempt that season. Windows count ATTEMPTS, not games, and cross season boundaries: `cur` is the make rate over the last `n` attempts through the season (`n < window_n` only for a short career, `qualified = false`); `prev` is the window before it, `season_start` the window entering the season and `career_baseline` every attempt before `cur`'s window -- each null rather than partial when there is not a full window of history. `delta_prev_rank` is 1 for the biggest riser among qualified rows with a `prev`. Attempts are regular-season and playoff shots only (`season_type_id` 2 and 4 -- play-in and NBA Cup final games are not counted), ordered by game date, period and clock. Ids are stats.nba.com ids as text with `id_source = "nba_stats"`; `entity_name` is the family name the shots carry. Span 1997-present, the shots' own span (END-year seasons: 1997 = 1996-97).

| | |
|---|---|
| **Builder** | [`python/nba_stats_17_rolling_windows_creation.py`](../../python/nba_stats_17_rolling_windows_creation.py) |
| **Release tag** | [`nba_stats_rolling_windows`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_rolling_windows) |
| **File stem** | `rolling_windows_{season}.{parquet,csv,rds}` |
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
| `entity_type` | String | Which aggregate the row is: "league" (every counted attempt that season), "team" or "player" on metric_curves; always "player" on rolling_windows. |
| `entity_id` | String | stats.nba.com id of the entity as TEXT -- the team_id on a team row, the person_id on a player row, null on the league row. |
| `entity_name` | String | Label for the entity: the team tricode ("GSW") on a team row, the shooter's name as the pbp ships it on a player row; null on the league row. |
| `team_id` | String | stats.nba.com team id (e.g. 1610612737 = Atlanta Hawks). |
| `metric` | String | What the row measures: "fg_pct_by_shot_distance" on metric_curves (field-goal percentage by shot distance in feet); "fg_pct" (window_unit "fga") or "fg3_pct" (window_unit "fg3a") on rolling_windows. |
| `window_unit` | String | What the window counts: "fga" (every field-goal attempt) or "fg3a" (three-point attempts). Regular-season and playoff attempts only. |
| `window_n` | Int64 | Window size in attempts (50 or 200), not games. |
| `cur` | Float64 | Make rate over the player's last n attempts through the season (the current window). |
| `prev` | Float64 | Make rate over the window_n attempts just before the current window; null unless that whole window exists. |
| `season_start` | Float64 | Make rate over the window_n attempts just before the season began (form entering the season); null unless the career before the season holds a full window. |
| `career_baseline` | Float64 | Make rate over every career attempt (since 1996-97) before the current window, earlier games of this season included; null unless that history holds at least window_n attempts. |
| `delta_prev` | Float64 | cur - prev; null when either side is null. |
| `delta_season` | Float64 | cur - season_start; null when either side is null. |
| `delta_career` | Float64 | cur - career_baseline; null when either side is null. |
| `delta_prev_rank` | Int64 | Rank of delta_prev within (window_unit, window_n, metric), 1 = biggest riser, ties share the lowest rank; null unless the row is qualified and has a prev. |
| `n` | Int64 | Attempts the current window averages: window_n, or fewer for a career shorter than the window. |
| `qualified` | Boolean | True when n == window_n (a full window, not a short career). Filter on it before ranking or comparing players. |
| `last_event_date` | Date | Date of the player's latest counted attempt through the season. |
| `as_of_date` | Date | Date of the latest counted attempt league-wide that season: the date the windows are current through. |
| `id_source` | String | Namespace of `entity_id` / `team_id` on this row -- "nba_stats" here; the cross-league contract carries "espn", "gsis" and "wnba_stats" elsewhere. |

## Coverage

_Coverage is tracked per release asset on [`nba_stats_rolling_windows`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_rolling_windows)._
