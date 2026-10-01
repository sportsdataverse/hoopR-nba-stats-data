# `officials`

NBA Stats Officials from hoopR data repository — `boxscoresummaryv2` (game-level).

| | |
|---|---|
| **Builder** | [`python/nba_stats_12_officials_creation.py`](../../python/nba_stats_12_officials_creation.py) |
| **Release tag** | [`nba_stats_officials`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_officials) |
| **File stem** | `officials_{season}.{parquet,csv,rds}` |
| **Seasons built** | 1997–2026 (30 seasons) |
| **Last published** | 2026-10-01 (newest release asset) |
| **Tag created** | 2026-07-24 |
| **Release assets** | 94 |

## Automation

`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the stage-99 schedule master is restamped at the end of every run.

## Columns

| col_name | type | description |
|---|---|---|
| `official_id` | Int64 | stats.nba.com person id of the game official. |
| `first_name` | String |  |
| `last_name` | String |  |
| `jersey_num` | String |  |
| `season` | Int64 | Season the row belongs to, as the season's ENDING year Int (2024 = the 2023-24 season), matching the asset filename -- on the reshaped RELEASE assets (the 2026-08-13 republish moved every `nba_stats_*` asset onto END-year names) and on the stage-99 master artifacts committed to `nba_stats/` (`schedule_master`, `games_in_data_repo`; the span STRING "1996-97" they carried until 2026-09-30 is gone). `draft` and `draft_combine` are an Int in a second sense: the four-digit draft year (2003 = the June 2003 draft, which precedes the 2003-04 season). |
| `game_id` | String | stats.nba.com game id, zero-padded 10-char string ("0022300001"; the "00" prefix is the NBA league id, so the id must never round-trip through int). |
| `season_type_id` | String | Season-type digit: the 3rd character of game_id (and the leading digit of season_id). 1 = preseason, 2 = regular season, 3 = All-Star, 4 = playoffs, 5 = play-in, 6 = NBA Cup final, 9 = international. |

## Coverage

| season | games built | games known |
|---:|---:|---:|
| 1997 | 42 | 1,261 |
| 1998 | 26 | 1,261 |
| 1999 | 21 | 791 |
| 2000 | 23 | 1,264 |
| 2001 | 41 | 1,261 |
| 2002 | 108 | 1,260 |
| 2003 | 22 | 1,277 |
| 2004 | 1,271 | 1,272 |
| 2005 | 1,314 | 1,315 |
| 2006 | 1,319 | 1,322 |
| 2007 | 1,309 | 1,310 |
| 2008 | 1,314 | 1,317 |
| 2009 | 1,315 | 1,317 |
| 2010 | 1,312 | 1,315 |
| 2011 | 1,311 | 1,433 |
| 2012 | 1,074 | 1,107 |
| 2013 | 1,314 | 1,433 |
| 2014 | 1,319 | 1,437 |
| 2015 | 1,311 | 1,431 |
| 2016 | 1,316 | 1,427 |
| 2017 | 1,309 | 1,412 |
| 2018 | 1,312 | 1,392 |
| 2019 | 1,312 | 1,394 |
| 2020 | 1,143 | 1,146 |
| 2021 | 1,171 | 1,221 |
| 2022 | 1,323 | 1,393 |
| 2023 | 1,320 | 1,394 |
| 2024 | 1,319 | 1,396 |
| 2025 | 1,321 | 1,400 |
| 2026 | 1,319 | 1,400 |
