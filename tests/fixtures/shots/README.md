# `tests/fixtures/shots/` -- the masked three-point distance

Real captures, trimmed, in the raw-store layout `build_pbp` reads
(`playbyplayv3/{END-year season}/{game_id}.json`). Used by
`tests/test_reshape_build.py::test_shots_*`.

stats.nba.com `playbyplayv3` reports `shotDistance` 0 for every three whose
legacy distance `sqrt(xLegacy^2 + yLegacy^2) / 10` is under 23.5 ft -- the
corner, and in 1994-97 the 22-ft line all round. Every other shot's
`shotDistance` is exactly `floor(distance + 0.5)`. Measured over all 30
published `nba_stats_shots` seasons (1997-2026, 2026-10-08): no exceptions either
way.

## `playbyplayv3/2026/0022500001.json`

2025-26 opener, OKC vs HOU. Sliced from
`hoopR-nba-stats-raw/nba_stats/json/playbyplayv3/2026/0022500001.json`
(request `http://nba.cloud/games/0022500001/playbyplay?Format=json`, captured
2026-02-04T11:40:08Z per its `meta.time`). `meta` and `game` kept verbatim; the
`actions` list is cut to 47 verbatim actions: all 22 threes at `shotDistance` 0,
the first 10 deeper threes, 6 twos at 0 ft, 6 longer twos, 3 non-shot actions.

## `playbyplayv3/1997/0029600360.json`

1996-97 regular season. Sliced from the same store
(`playbyplayv3/1997/0029600360.json`, captured 2025-02-17T14:07:48Z): 11 threes,
4 at legacy (0, 0) -- no location -- 4 located at 22-23 ft (reported 0), and 3 at 24 ft.

## `shotchartdetail_0022500001.json`

The ground truth for the 2025-26 slice: a live `stats.nba.com/stats/shotchartdetail`
call (`GameID=0022500001`, `Season=2025-26`, `SeasonType=Regular Season`,
`ContextMeasure=FGA`, `TeamID=0`, `PlayerID=0`; curl_cffi `impersonate="chrome"`,
2026-10-08), `rowSet` cut to the 44 field goals in the pbp slice. `LOC_X`/`LOC_Y`
equal `xLegacy`/`yLegacy` on every row, and `SHOT_DISTANCE` is
`floor(distance)`: 22-23 ft on the corner threes the play-by-play reports as 0.
