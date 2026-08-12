# `tests/fixtures/raw/` -- offline processor oracle

Verbatim raw-store layout (`nba_stats/json/{kind}/{game_id}.json`, matching
`nba_data_build.scrape.raw_store`) used by `tests/test_process_from_raw.py` to
exercise `nba_data_build.process.from_raw.process_game` with zero network
access.

## `leaguegamelog/2024/regular-season.json` -- neutral-site pivot regression

Real `leaguegamelog` rows sliced verbatim out of
`hoopR-nba-stats-raw/nba_stats/json/leaguegamelog/2024/regular-season.json`
(captured 2026-08; headers and `parameters` preserved) for three games:

- `0022400147` -- Mexico City Game 2024 (`WAS @ MIA` / `MIA @ WAS`).
- `0022401230` -- NBA Cup final, Las Vegas (`OKC @ HOU` / `HOU @ OKC`).
- `0022400001` -- ordinary home game (`BOS vs. ATL`), the control.

Neutral-site games get `@` on BOTH rows, so `MATCHUP` alone cannot name the
host and `schedule_from_gamelog` falls back to the boxscore. Paired slices:

- `boxv3/0022400147.json`, `boxv3/0022401230.json` -- the real
  `boxscoretraditionalv3` payload with the `players` / `statistics` arrays
  dropped. `boxscore_home_away` reads only `homeTeamId` / `awayTeamId`, and the
  full captures are ~300 KB apiece.

Exercised by `tests/test_v3_backfill.py::test_schedule_from_gamelog_neutral_site_*`.

## `0022300001`

- `pbpv3/0022300001.json` -- verbatim copy of sdv-py's
  `tests/fixtures/nba_engine/0022300001/playbyplayv3.json` (real
  `playbyplayv3` capture).
- `boxv3/0022300001.json` -- verbatim copy of sdv-py's
  `tests/fixtures/nba_engine/0022300001/boxscoretraditionalv3.json` (real
  whole-game `boxscoretraditionalv3` capture).
- `boxv3_periods/0022300001.json` -- **fabricated placeholder**: a
  `{"1": <box>, "2": <box>, "3": <box>, "4": <box>}` dict built by repeating
  the same whole-game `boxscoretraditionalv3` payload above for each of the
  game's 4 regulation periods. Real per-period-scoped captures (via
  `RangeType=2` custom-range queries, see
  `nba_data_build/scrape/client.py::fetch_box_periods`) don't exist as a
  committed sdv-py fixture yet -- `players_on_court_from_quarter_boxscores`
  is a Tasks 1-3 sdv-py-side deliverable not on the pinned rev at the time
  this fixture was created (see `from_raw.py`'s module docstring for the
  fallback seam this unblocks). This placeholder is only exercised for its
  *shape* (int-castable keys -> per-period boxscore dict) by the current
  fallback path; it is NOT asserted for period-scoped lineup accuracy. Replace
  with real per-period captures once upstream ships the quarter-box function
  and re-validate `test_process_uses_quarter_box_source` accordingly.
