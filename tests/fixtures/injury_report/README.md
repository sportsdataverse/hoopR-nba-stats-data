# injury_report fixture

These are real rows, trimmed, for `tests/test_injury_report.py`. `make_fixture.py` regenerates them from the sibling `hoopR-nba-stats-raw` checkout and this repo's committed `nba_stats/` tree (captured 2026-10-30).

- `raw/injury_report/2026/2026-01-08.json`: two of the day's report versions. The first lists a team as NOT YET SUBMITTED; the second is the day's last.
- `raw/injury_report/2026/2026-07-15.json`: the day's last Summer League version.
- `nba_stats/nba_stats_schedule_master.parquet`: the 2025-26 games on 2026-01-08, 01-09 and 01-29 for the teams on the January reports. 01-29 holds MIA@CHI, which was postponed from 01-08.
- `nba_stats/player_boxscores/parquet/player_boxscores_2026.parquet`: `team_id, person_id, first_name, family_name` for those teams.
- `nba_stats/rosters/parquet/rosters_2026.parquet`: `team_id, player_id, player` for those teams.
