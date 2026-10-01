# `metric_curves`

NBA Stats Metric Curves from hoopR data repository — `derived` (derived-level).

FG% by shot distance -- league, team and player curves per season, computed by `sportsdataverse.metric_curves` from the committed `nba_stats_shots`. One row per (season, entity, bucket): 1-ft bins from 0 to 35 ft, then 35-50 and 50-95 ft (`x_lo` inclusive, `x_hi` exclusive), each carrying `attempts`, `successes` (makes) and `rate = successes / attempts`; an empty bucket is absent, never a zero row. Attempts are regular-season and playoff shots only (`season_type_id` 2 and 4 -- play-in and NBA Cup final games are not counted). Ids are stats.nba.com ids as text with `id_source = "nba_stats"`: `entity_id` is the `team_id` / `person_id` (null on the league row), `team_id` on a player row is the team of most of that player's attempts. `down` and `epa_per_att` are null on every row (the cross-league contract's football-only columns). Span 1997-present, the shots' own span (END-year seasons: 1997 = 1996-97).

| | |
|---|---|
| **Builder** | [`python/nba_stats_18_metric_curves_creation.py`](../../python/nba_stats_18_metric_curves_creation.py) |
| **Release tag** | [`nba_stats_metric_curves`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_metric_curves) |
| **File stem** | `metric_curves_{season}.{parquet,csv,rds}` |
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
| `entity_type` | String | Which aggregate the row is: "league" (every counted attempt that season), "team" or "player". |
| `entity_id` | String | stats.nba.com id of the entity as TEXT -- the team_id on a team row, the person_id on a player row, null on the league row. |
| `entity_name` | String | Label for the entity: the team tricode ("GSW") on a team row, the shooter's name as the pbp ships it on a player row; null on the league row. |
| `team_id` | String | stats.nba.com team id (e.g. 1610612737 = Atlanta Hawks). |
| `id_source` | String | Namespace of `entity_id` / `team_id` on this row -- "nba_stats" here; the cross-league contract carries "espn", "gsis" and "wnba_stats" elsewhere. |
| `metric` | String | Curve name: "fg_pct_by_shot_distance" (field-goal percentage by shot distance in feet). |
| `down` | Int64 | Null on every row: the second axis of the football-only success_by_down_distance curve, carried for the cross-league contract. |
| `x_lo` | Float64 | Bucket lower edge in feet, inclusive: 1-ft bins from 0 to 35, then 35 and 50. |
| `x_hi` | Float64 | Bucket upper edge in feet, exclusive: x_lo + 1 below 35 ft, then 50 and 95. |
| `attempts` | Int64 | Field-goal attempts in the bucket -- regular-season and playoff shots only (season_type_id 2 and 4; play-in and NBA Cup final games are not counted). An empty bucket is absent, never a zero row. |
| `successes` | Int64 | Made field goals in the bucket. |
| `rate` | Float64 | successes / attempts, one exact division (no smoothing or prior). |
| `epa_per_att` | Float64 | Null on every row: shots carry no EPA. Populated on the football twins of this contract. |

## Coverage

_Coverage is tracked per release asset on [`nba_stats_metric_curves`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_metric_curves)._
