# prior_informed fixture (BB-D38 / BB-D39)

Real NBA data for `tests/test_prior_informed.py`. Rows are filtered and columns dropped; nothing is
edited or synthetic. Rebuilt by `build_fixture.py` (2026-11-12) from the hoopR-nba-stats-raw checkout at
`cee4198fa8`, the local possession cache (`compile_nba_season`, lineup source `auto`) and the
sportsdataverse-py `tools/fit_box_prior_v2.py` run behind BB-D38 (sdv-py #1165).

| file | what |
|---|---|
| `possessions_2014_2015.parquet` | Regular-season possessions of 2013-14 dated 2014-04-01 or later and of 2014-15 dated before 2014-11-08 (`game_id, game_date, season, points, offense/defense_team_id`, lineups). |
| `leaguegamelog_2014_2015.parquet` | The raw store's `leaguegamelog` rows (player `_pt == "P"`, team `"T"`) of the same games; `_season` = END year. |
| `playerindex_2015.parquet` / `biostats_2015.parquet` | 2014-15 `playerindex` and `leaguedashplayerbiostats` rows of the players on court in those possessions. |
| `d38_fit_features_priors.parquet` | The fit's own `feat_{s}.parquet` rows and `prior_{s}.parquet` priors for the 40 highest-possession players of 2004, 2010 and 2024: `models/box_prior_v2.json` must reproduce those priors. |
