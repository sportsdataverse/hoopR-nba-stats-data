# `player_season_stats`

NBA Stats Player Season Stats from hoopR data repository — `leaguedashplayerstats` (season-level).

| | |
|---|---|
| **Builder** | [`python/nba_stats_02_player_season_stats_creation.py`](../../python/nba_stats_02_player_season_stats_creation.py) |
| **Release tag** | [`nba_stats_player_season_stats`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_player_season_stats) |
| **File stem** | `player_season_stats_{season}.{parquet,csv,rds}` |
| **Seasons built** | — |
| **Last published** | 2026-07-24 (newest release asset) |
| **Tag created** | 2026-07-24 |
| **Release assets** | 90 |

## Automation

`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the stage-99 schedule master is restamped at the end of every run.

## Columns

| col_name | type | description |
|---|---|---|
| `player_id` | Int64 | stats.nba.com person id of the player (Int64); joins rosters, boxscores, game logs and pbp (`person_id`). |
| `player_name` | String | Player display name as the stats API ships it ("LeBron James"). |
| `nickname` | String |  |
| `team_id` | Int64 | stats.nba.com team id (Int64, e.g. 1610612737 = Atlanta Hawks). |
| `team_abbreviation` | String | Three-letter team code ("ATL"). |
| `age` | Float64 |  |
| `gp` | Int64 |  |
| `w` | Int64 |  |
| `l` | Int64 |  |
| `w_pct` | Float64 |  |
| `min` | Float64 | Team (or player) minutes in the log row. |
| `e_off_rating` | Float64 |  |
| `off_rating` | Float64 |  |
| `sp_work_off_rating` | Float64 |  |
| `e_def_rating` | Float64 |  |
| `def_rating` | Float64 |  |
| `sp_work_def_rating` | Float64 |  |
| `e_net_rating` | Float64 |  |
| `net_rating` | Float64 |  |
| `sp_work_net_rating` | Float64 |  |
| `ast_pct` | Float64 |  |
| `ast_to` | Float64 |  |
| `ast_ratio` | Float64 |  |
| `oreb_pct` | Float64 |  |
| `dreb_pct` | Float64 |  |
| `reb_pct` | Float64 |  |
| `tm_tov_pct` | Float64 |  |
| `e_tov_pct` | Float64 |  |
| `efg_pct` | Float64 |  |
| `ts_pct` | Float64 |  |
| `usg_pct` | Float64 |  |
| `e_usg_pct` | Float64 |  |
| `e_pace` | Float64 |  |
| `pace` | Float64 |  |
| `pace_per40` | Float64 |  |
| `sp_work_pace` | Float64 |  |
| `pie` | Float64 |  |
| `poss` | Int64 |  |
| `fgm` | Float64 | Field goals made. |
| `fga` | Float64 | Field goals attempted. |
| `fgm_pg` | Float64 |  |
| `fga_pg` | Float64 |  |
| `fg_pct` | Float64 | Field-goal percentage (0-1). |
| `gp_rank` | Int64 |  |
| `w_rank` | Int64 |  |
| `l_rank` | Int64 |  |
| `w_pct_rank` | Int64 |  |
| `min_rank` | Int64 |  |
| `e_off_rating_rank` | Int64 |  |
| `off_rating_rank` | Int64 |  |
| `sp_work_off_rating_rank` | Int64 |  |
| `e_def_rating_rank` | Int64 |  |
| `def_rating_rank` | Int64 |  |
| `sp_work_def_rating_rank` | Int64 |  |
| `e_net_rating_rank` | Int64 |  |
| `net_rating_rank` | Int64 |  |
| `sp_work_net_rating_rank` | Int64 |  |
| `ast_pct_rank` | Int64 |  |
| `ast_to_rank` | Int64 |  |
| `ast_ratio_rank` | Int64 |  |
| `oreb_pct_rank` | Int64 |  |
| `dreb_pct_rank` | Int64 |  |
| `reb_pct_rank` | Int64 |  |
| `tm_tov_pct_rank` | Int64 |  |
| `e_tov_pct_rank` | Int64 |  |
| `efg_pct_rank` | Int64 |  |
| `ts_pct_rank` | Int64 |  |
| `usg_pct_rank` | Int64 |  |
| `e_usg_pct_rank` | Int64 |  |
| `e_pace_rank` | Int64 |  |
| `pace_rank` | Int64 |  |
| `sp_work_pace_rank` | Int64 |  |
| `pie_rank` | Int64 |  |
| `fgm_rank` | Int64 |  |
| `fga_rank` | Int64 |  |
| `fgm_pg_rank` | Int64 |  |
| `fga_pg_rank` | Int64 |  |
| `fg_pct_rank` | Int64 |  |
| `team_count` | Int64 |  |
| `season` | Int64 | Season the row belongs to. Stats-API span form for NBA ("2023-24") in the released season assets; the schedule master carries the same span form. `draft` is the exception: it carries the four-digit draft year as an integer (2003 = the June 2003 draft, which precedes the 2003-04 season). |
| `season_type` | String | Season type the capture was made under ("Regular Season", "Playoffs", ...). |
| `measure_type` | String |  |
| `per_mode` | String |  |
| `fg3m` | Float64 | Three-point field goals made. |
| `fg3a` | Float64 | Three-point field goals attempted. |
| `fg3_pct` | Float64 | Three-point percentage (0-1). |
| `ftm` | Float64 | Free throws made. |
| `fta` | Float64 | Free throws attempted. |
| `ft_pct` | Float64 | Free-throw percentage (0-1). |
| `oreb` | Float64 | Offensive rebounds. |
| `dreb` | Float64 | Defensive rebounds. |
| `reb` | Float64 | Total rebounds. |
| `ast` | Float64 | Assists. |
| `tov` | Float64 | Turnovers. |
| `stl` | Float64 | Steals. |
| `blk` | Float64 | Blocks. |
| `blka` | Float64 |  |
| `pf` | Float64 | Personal fouls. |
| `pfd` | Float64 |  |
| `pts` | Float64 | Points. |
| `plus_minus` | Float64 | Point differential while on the floor (player rows) or final margin (team rows). |
| `nba_fantasy_pts` | Float64 |  |
| `dd2` | Int64 |  |
| `td3` | Int64 |  |
| `wnba_fantasy_pts` | Float64 |  |
| `fg3m_rank` | Int64 |  |
| `fg3a_rank` | Int64 |  |
| `fg3_pct_rank` | Int64 |  |
| `ftm_rank` | Int64 |  |
| `fta_rank` | Int64 |  |
| `ft_pct_rank` | Int64 |  |
| `oreb_rank` | Int64 |  |
| `dreb_rank` | Int64 |  |
| `reb_rank` | Int64 |  |
| `ast_rank` | Int64 |  |
| `tov_rank` | Int64 |  |
| `stl_rank` | Int64 |  |
| `blk_rank` | Int64 |  |
| `blka_rank` | Int64 |  |
| `pf_rank` | Int64 |  |
| `pfd_rank` | Int64 |  |
| `pts_rank` | Int64 |  |
| `plus_minus_rank` | Int64 |  |
| `nba_fantasy_pts_rank` | Int64 |  |
| `dd2_rank` | Int64 |  |
| `td3_rank` | Int64 |  |
| `wnba_fantasy_pts_rank` | Int64 |  |
| `pct_dreb` | Float64 |  |
| `pct_stl` | Float64 |  |
| `pct_blk` | Float64 |  |
| `opp_pts_off_tov` | Float64 |  |
| `opp_pts_2nd_chance` | Float64 |  |
| `opp_pts_fb` | Float64 |  |
| `opp_pts_paint` | Float64 |  |
| `def_ws` | Float64 |  |
| `def_ws_raw` | Float64 |  |
| `pct_dreb_rank` | Int64 |  |
| `pct_stl_rank` | Int64 |  |
| `pct_blk_rank` | Int64 |  |
| `opp_pts_off_tov_rank` | Int64 |  |
| `opp_pts_2nd_chance_rank` | Int64 |  |
| `opp_pts_fb_rank` | Int64 |  |
| `opp_pts_paint_rank` | Int64 |  |
| `def_ws_rank` | Int64 |  |
| `pts_off_tov` | Float64 |  |
| `pts_2nd_chance` | Float64 |  |
| `pts_fb` | Float64 |  |
| `pts_paint` | Float64 |  |
| `pts_off_tov_rank` | Int64 |  |
| `pts_2nd_chance_rank` | Int64 |  |
| `pts_fb_rank` | Int64 |  |
| `pts_paint_rank` | Int64 |  |
| `pct_fga_2pt` | Float64 |  |
| `pct_fga_3pt` | Float64 |  |
| `pct_pts_2pt` | Float64 |  |
| `pct_pts_2pt_mr` | Float64 |  |
| `pct_pts_3pt` | Float64 |  |
| `pct_pts_fb` | Float64 |  |
| `pct_pts_ft` | Float64 |  |
| `pct_pts_off_tov` | Float64 |  |
| `pct_pts_paint` | Float64 |  |
| `pct_ast_2pm` | Float64 |  |
| `pct_uast_2pm` | Float64 |  |
| `pct_ast_3pm` | Float64 |  |
| `pct_uast_3pm` | Float64 |  |
| `pct_ast_fgm` | Float64 |  |
| `pct_uast_fgm` | Float64 |  |
| `pct_fga_2pt_rank` | Int64 |  |
| `pct_fga_3pt_rank` | Int64 |  |
| `pct_pts_2pt_rank` | Int64 |  |
| `pct_pts_2pt_mr_rank` | Int64 |  |
| `pct_pts_3pt_rank` | Int64 |  |
| `pct_pts_fb_rank` | Int64 |  |
| `pct_pts_ft_rank` | Int64 |  |
| `pct_pts_off_tov_rank` | Int64 |  |
| `pct_pts_paint_rank` | Int64 |  |
| `pct_ast_2pm_rank` | Int64 |  |
| `pct_uast_2pm_rank` | Int64 |  |
| `pct_ast_3pm_rank` | Int64 |  |
| `pct_uast_3pm_rank` | Int64 |  |
| `pct_ast_fgm_rank` | Int64 |  |
| `pct_uast_fgm_rank` | Int64 |  |
| `pct_fgm` | Float64 |  |
| `pct_fga` | Float64 |  |
| `pct_fg3m` | Float64 |  |
| `pct_fg3a` | Float64 |  |
| `pct_ftm` | Float64 |  |
| `pct_fta` | Float64 |  |
| `pct_oreb` | Float64 |  |
| `pct_reb` | Float64 |  |
| `pct_ast` | Float64 |  |
| `pct_tov` | Float64 |  |
| `pct_blka` | Float64 |  |
| `pct_pf` | Float64 |  |
| `pct_pfd` | Float64 |  |
| `pct_pts` | Float64 |  |
| `pct_fgm_rank` | Int64 |  |
| `pct_fga_rank` | Int64 |  |
| `pct_fg3m_rank` | Int64 |  |
| `pct_fg3a_rank` | Int64 |  |
| `pct_ftm_rank` | Int64 |  |
| `pct_fta_rank` | Int64 |  |
| `pct_oreb_rank` | Int64 |  |
| `pct_reb_rank` | Int64 |  |
| `pct_ast_rank` | Int64 |  |
| `pct_tov_rank` | Int64 |  |
| `pct_blka_rank` | Int64 |  |
| `pct_pf_rank` | Int64 |  |
| `pct_pfd_rank` | Int64 |  |
| `pct_pts_rank` | Int64 |  |

## Coverage

_Coverage is tracked per release asset on [`nba_stats_player_season_stats`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_player_season_stats)._
