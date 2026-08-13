# NBA v3 raw-store coverage probe

- **Store root:** `/mnt/sdv_repos/hoopR-nba-stats-raw/nba_stats/json`
- **Seasons:** 1996-2026 (start-year labels)
- **Sampling:** up to 20 files per (endpoint, season) parsed for emptiness
- **Populated** = a payload carrying > 0 rows (resultSets rowSet / pbp `game.actions` / `boxScoreTraditional` players). An empty 200 is not coverage.

Game endpoints (`playbyplayv3`, `boxscoresummaryv2`, `boxscoretraditionalv3`) are read from the **end-year** dir (`start + 1`); all others from the **start-year** dir. The `dir` column below states which directory was read.

## Season floors (feed `datasets.py` `season_floor`)

| endpoint | dir keying | floor (start year) | total files |
|---|---|---|---|
| `playbyplayv3` | end (start+1) | 1996 | 37,987 |
| `boxscoresummaryv2` | end (start+1) | 1996 | 37,853 |
| `boxscoretraditionalv3` | end (start+1) | 1996 | 37,987 |
| `leaguestandingsv3` | start | 1996 | 62 |
| `leaguedashplayerstats` | start | 1996 | 868 |
| `leaguedashteamstats` | start | 1996 | 868 |
| `leaguedashlineups` | start | 2007 | 868 |
| `commonteamroster` | start | 1996 | 879 |
| `leaguegamelog` | start | 1996 | 62 |
| `drafthistory` | start | **NONE (no populated season)** | 0 |

## Dataset season floors (the value that lands in `datasets.py`)

Each of the 15 target datasets inherits its source endpoint's floor. `shots` derives
from `playbyplayv3`; `draft` has no data until the Phase 3 capture.

| dataset key | source endpoint | season_floor |
|---|---|---|
| standings | leaguestandingsv3 | 1996 |
| player_season_stats | leaguedashplayerstats | 1996 |
| team_season_stats | leaguedashteamstats | 1996 |
| lineups | leaguedashlineups | **2007** |
| rosters | commonteamroster | 1996 |
| coaches | commonteamroster | 1996 |
| draft | drafthistory | **pending capture (Phase 3)** |
| schedules | leaguegamelog | 1996 |
| player_game_logs | leaguegamelog | 1996 |
| pbp | playbyplayv3 | 1996 |
| game_rosters | boxscoresummaryv2 | 1996 |
| officials | boxscoresummaryv2 | 1996 |
| player_boxscores | boxscoretraditionalv3 | 1996 |
| team_boxscores | boxscoretraditionalv3 | 1996 |
| shots | playbyplayv3 (derived) | 1996 |

## Notes & risks

- **`leaguedashlineups` floor is 2007, not 1996.** Files exist for 1996-2006 but are
  empty 200s (NBA tracking-style lineup data begins 2007-08). `lineups` must produce no
  artifact for start years < 2007. This is the one endpoint with a floor above 1996.
- **`drafthistory` is absent everywhere (0 files).** The `draft` dataset cannot build until
  the Phase 3 `-raw` capture lands it. Treat as a hard prerequisite, not a floor.
- **Upper ceiling is start-year 2025 (2025-26), not 2026.** The 2026-27 season is unplayed
  (today 2026-07): game endpoints have no `2027` end-year dir (0 files); league endpoints
  wrote empty 200s into their `2026` start-year dir (populated=0 above). Building start-year
  2026 yields nothing — expected, not a gap. `commonteamroster` has no `2026` dir at all.
- **`boxscoresummaryv2` floor uses "any resultSet populated".** The two datasets it feeds
  read specific resultSets: `officials` (Officials) and `game_rosters` (InactivePlayers).
  `InactivePlayers` can legitimately be empty for an individual game (no inactive players),
  so `game_rosters` will have per-game sparsity even where the endpoint is covered — that is
  data, not a coverage hole. Both are covered from 1996.
- **`playbyplayv3` 1998 (dir 1999) shows fewer files (791)** — the lockout-shortened 1998-99
  season (50 games/team), not a coverage gap.

## Play-by-play coverage by game type

Program V publishes **every** NBA season type for 1997–2026 (END-year) —
preseason (`001`), regular season (`002`), All-Star (`003`), playoffs (`004`),
play-in (`005`) and NBA Cup final (`006`). The schedule is therefore the full
game universe, and it carries games the `playbyplayv3` feed has no actions for.
Counts below are the staged v3 build as verified **2026-08-12/13**:

| season type | scheduled | with play-by-play | without |
|---|---:|---:|---:|
| preseason (`001`) | 2,836 | 1,267 | 1,569 |
| regular season (`002`) | 35,547 | 35,546 | 1 |
| All-Star (`003`) | 96 | 66 | 30 |
| playoffs (`004`) | 2,442 | 2,440 | 2 |
| play-in (`005`) | 37 | 37 | 0 |
| NBA Cup final (`006`) | 3 | 3 | 0 |
| **total** | **40,961** | **39,359** | **1,602** |

- **Preseason play-by-play begins with the 2010-11 season** (END-year 2011).
  Every preseason game from 2011 onward has play-by-play; none from 1996-97
  through 2009-10 does. The boundary is clean rather than scattered — END-year
  2010 is 0 of 119, END-year 2011 is 119 of 119 — which is what an era boundary
  looks like and a capture gap does not. Two later preseason dates are the only
  exceptions: `0011300114` (MIL vs. TOR, 2013-10-25, 0-0) and `0011600107`
  (CHI vs. BOS, 2016-10-22, unscored) — never-played dates, not lost captures.
- **All-Star (30 of 96) are exhibition events, not games** — the Rookie
  Challenge (`SPH vs. RKE`) and the Skills/Shooting events published under
  `EST`/`WST` matchups. The All-Star Game itself has play-by-play.
- **Playoffs (2) are phantom placeholders.** `0040401000` and `0040401001` are
  dated 2005-06-27 and 2005-06-28 — *after* the 2005 Finals ended — with no
  teams and no scores. Never-played "if necessary" dates; upstream files them
  the same way each year (2025-26 carries `0042500406`/`0042500407`).
- **Regular season (1) is `0021201214`** (BOS vs. IND, 2013-04-16), the game
  cancelled after the Boston Marathon bombing. It is present in the raw
  `leaguegamelog` at 0-0, so it is correctly carried with no play-by-play.

**These are upstream absences and should NOT be re-scraped.** Each payload is a
*valid* response with `actions: []`, not a fetch failure: a live re-probe returns
`keys=['game','meta']` with 0 actions on the same session that returns 500+
actions for other games — a positive control ruling out rate limiting, session
death, and IP blocking. Upstream may publish more later; this records what it
served as of 2026-08-12/13.

**Maintainers: `games_no_pbp` is not `games_failed`.** The per-season build
summary (`v3_staging/nba_build_summary_{season}.json`) counts them separately,
and `v3_gate` reads both. `games_failed` is a game the build could not process
(a missing capture, a parse error) and is exit-code-worthy; `games_no_pbp` is a
game upstream served empty and is the expected steady state — currently 1,602
across 1997–2026 with `games_failed=0`. Re-running the backfill will not change
`games_no_pbp`, and a re-capture is only ever the answer to `games_uncaptured`.

## `playbyplayv3`

- floor (start year): **1996**
- total files: 37,987

| season (start) | dir | files | sampled | populated | empty |
|---|---|---|---|---|---|
| **1996** ◀ floor | 1997 | 1261 | 20 | 20 | 0 |
| 1997 | 1998 | 1260 | 20 | 20 | 0 |
| 1998 | 1999 | 791 | 20 | 20 | 0 |
| 1999 | 2000 | 1264 | 20 | 20 | 0 |
| 2000 | 2001 | 1260 | 20 | 20 | 0 |
| 2001 | 2002 | 1260 | 20 | 20 | 0 |
| 2002 | 2003 | 1277 | 20 | 20 | 0 |
| 2003 | 2004 | 1271 | 20 | 20 | 0 |
| 2004 | 2005 | 1314 | 20 | 20 | 0 |
| 2005 | 2006 | 1319 | 20 | 20 | 0 |
| 2006 | 2007 | 1309 | 20 | 20 | 0 |
| 2007 | 2008 | 1316 | 20 | 20 | 0 |
| 2008 | 2009 | 1315 | 20 | 20 | 0 |
| 2009 | 2010 | 1312 | 20 | 20 | 0 |
| 2010 | 2011 | 1311 | 20 | 20 | 0 |
| 2011 | 2012 | 1074 | 20 | 20 | 0 |
| 2012 | 2013 | 1315 | 20 | 20 | 0 |
| 2013 | 2014 | 1319 | 20 | 20 | 0 |
| 2014 | 2015 | 1311 | 20 | 20 | 0 |
| 2015 | 2016 | 1316 | 20 | 20 | 0 |
| 2016 | 2017 | 1309 | 20 | 20 | 0 |
| 2017 | 2018 | 1312 | 20 | 20 | 0 |
| 2018 | 2019 | 1312 | 20 | 20 | 0 |
| 2019 | 2020 | 1142 | 20 | 20 | 0 |
| 2020 | 2021 | 1165 | 20 | 20 | 0 |
| 2021 | 2022 | 1317 | 20 | 20 | 0 |
| 2022 | 2023 | 1314 | 20 | 20 | 0 |
| 2023 | 2024 | 1312 | 20 | 20 | 0 |
| 2024 | 2025 | 1314 | 20 | 20 | 0 |
| 2025 | 2026 | 1315 | 20 | 20 | 0 |
| 2026 | 2027 | 0 | 0 | 0 | 0 |

## `boxscoresummaryv2`

- floor (start year): **1996**
- total files: 37,853

| season (start) | dir | files | sampled | populated | empty |
|---|---|---|---|---|---|
| **1996** ◀ floor | 1997 | 1261 | 20 | 20 | 0 |
| 1997 | 1998 | 1260 | 20 | 20 | 0 |
| 1998 | 1999 | 791 | 20 | 20 | 0 |
| 1999 | 2000 | 1264 | 20 | 20 | 0 |
| 2000 | 2001 | 1260 | 20 | 20 | 0 |
| 2001 | 2002 | 1260 | 20 | 20 | 0 |
| 2002 | 2003 | 1277 | 20 | 20 | 0 |
| 2003 | 2004 | 1271 | 20 | 20 | 0 |
| 2004 | 2005 | 1314 | 20 | 20 | 0 |
| 2005 | 2006 | 1319 | 20 | 20 | 0 |
| 2006 | 2007 | 1297 | 20 | 20 | 0 |
| 2007 | 2008 | 1316 | 20 | 20 | 0 |
| 2008 | 2009 | 1315 | 20 | 20 | 0 |
| 2009 | 2010 | 1312 | 20 | 20 | 0 |
| 2010 | 2011 | 1311 | 20 | 20 | 0 |
| 2011 | 2012 | 1074 | 20 | 20 | 0 |
| 2012 | 2013 | 1314 | 20 | 20 | 0 |
| 2013 | 2014 | 1319 | 20 | 20 | 0 |
| 2014 | 2015 | 1311 | 20 | 20 | 0 |
| 2015 | 2016 | 1316 | 20 | 20 | 0 |
| 2016 | 2017 | 1309 | 20 | 20 | 0 |
| 2017 | 2018 | 1312 | 20 | 20 | 0 |
| 2018 | 2019 | 1311 | 20 | 20 | 0 |
| 2019 | 2020 | 1141 | 20 | 20 | 0 |
| 2020 | 2021 | 1165 | 20 | 20 | 0 |
| 2021 | 2022 | 1317 | 20 | 20 | 0 |
| 2022 | 2023 | 1314 | 20 | 20 | 0 |
| 2023 | 2024 | 1312 | 20 | 20 | 0 |
| 2024 | 2025 | 1230 | 20 | 20 | 0 |
| 2025 | 2026 | 1280 | 20 | 20 | 0 |
| 2026 | 2027 | 0 | 0 | 0 | 0 |

## `boxscoretraditionalv3`

- floor (start year): **1996**
- total files: 37,987

| season (start) | dir | files | sampled | populated | empty |
|---|---|---|---|---|---|
| **1996** ◀ floor | 1997 | 1261 | 20 | 20 | 0 |
| 1997 | 1998 | 1260 | 20 | 20 | 0 |
| 1998 | 1999 | 791 | 20 | 20 | 0 |
| 1999 | 2000 | 1264 | 20 | 20 | 0 |
| 2000 | 2001 | 1260 | 20 | 20 | 0 |
| 2001 | 2002 | 1260 | 20 | 20 | 0 |
| 2002 | 2003 | 1277 | 20 | 20 | 0 |
| 2003 | 2004 | 1271 | 20 | 20 | 0 |
| 2004 | 2005 | 1314 | 20 | 20 | 0 |
| 2005 | 2006 | 1319 | 20 | 20 | 0 |
| 2006 | 2007 | 1309 | 20 | 20 | 0 |
| 2007 | 2008 | 1316 | 20 | 20 | 0 |
| 2008 | 2009 | 1315 | 20 | 20 | 0 |
| 2009 | 2010 | 1312 | 20 | 20 | 0 |
| 2010 | 2011 | 1311 | 20 | 20 | 0 |
| 2011 | 2012 | 1074 | 20 | 20 | 0 |
| 2012 | 2013 | 1315 | 20 | 20 | 0 |
| 2013 | 2014 | 1319 | 20 | 20 | 0 |
| 2014 | 2015 | 1311 | 20 | 20 | 0 |
| 2015 | 2016 | 1316 | 20 | 20 | 0 |
| 2016 | 2017 | 1309 | 20 | 20 | 0 |
| 2017 | 2018 | 1312 | 20 | 20 | 0 |
| 2018 | 2019 | 1312 | 20 | 20 | 0 |
| 2019 | 2020 | 1142 | 20 | 20 | 0 |
| 2020 | 2021 | 1165 | 20 | 20 | 0 |
| 2021 | 2022 | 1317 | 20 | 20 | 0 |
| 2022 | 2023 | 1314 | 20 | 20 | 0 |
| 2023 | 2024 | 1312 | 20 | 20 | 0 |
| 2024 | 2025 | 1314 | 20 | 20 | 0 |
| 2025 | 2026 | 1315 | 20 | 20 | 0 |
| 2026 | 2027 | 0 | 0 | 0 | 0 |

## `leaguestandingsv3`

- floor (start year): **1996**
- total files: 62

| season (start) | dir | files | sampled | populated | empty |
|---|---|---|---|---|---|
| **1996** ◀ floor | 1996 | 2 | 2 | 1 | 1 |
| 1997 | 1997 | 2 | 2 | 1 | 1 |
| 1998 | 1998 | 2 | 2 | 1 | 1 |
| 1999 | 1999 | 2 | 2 | 1 | 1 |
| 2000 | 2000 | 2 | 2 | 1 | 1 |
| 2001 | 2001 | 2 | 2 | 1 | 1 |
| 2002 | 2002 | 2 | 2 | 1 | 1 |
| 2003 | 2003 | 2 | 2 | 1 | 1 |
| 2004 | 2004 | 2 | 2 | 1 | 1 |
| 2005 | 2005 | 2 | 2 | 1 | 1 |
| 2006 | 2006 | 2 | 2 | 1 | 1 |
| 2007 | 2007 | 2 | 2 | 1 | 1 |
| 2008 | 2008 | 2 | 2 | 1 | 1 |
| 2009 | 2009 | 2 | 2 | 1 | 1 |
| 2010 | 2010 | 2 | 2 | 1 | 1 |
| 2011 | 2011 | 2 | 2 | 1 | 1 |
| 2012 | 2012 | 2 | 2 | 1 | 1 |
| 2013 | 2013 | 2 | 2 | 1 | 1 |
| 2014 | 2014 | 2 | 2 | 1 | 1 |
| 2015 | 2015 | 2 | 2 | 1 | 1 |
| 2016 | 2016 | 2 | 2 | 1 | 1 |
| 2017 | 2017 | 2 | 2 | 1 | 1 |
| 2018 | 2018 | 2 | 2 | 1 | 1 |
| 2019 | 2019 | 2 | 2 | 1 | 1 |
| 2020 | 2020 | 2 | 2 | 1 | 1 |
| 2021 | 2021 | 2 | 2 | 1 | 1 |
| 2022 | 2022 | 2 | 2 | 1 | 1 |
| 2023 | 2023 | 2 | 2 | 1 | 1 |
| 2024 | 2024 | 2 | 2 | 1 | 1 |
| 2025 | 2025 | 2 | 2 | 1 | 1 |
| 2026 | 2026 | 2 | 2 | 1 | 1 |

## `leaguedashplayerstats`

- floor (start year): **1996**
- total files: 868

| season (start) | dir | files | sampled | populated | empty |
|---|---|---|---|---|---|
| **1996** ◀ floor | 1996 | 28 | 20 | 15 | 5 |
| 1997 | 1997 | 28 | 20 | 14 | 6 |
| 1998 | 1998 | 28 | 20 | 16 | 4 |
| 1999 | 1999 | 28 | 20 | 14 | 6 |
| 2000 | 2000 | 28 | 20 | 16 | 4 |
| 2001 | 2001 | 28 | 20 | 15 | 5 |
| 2002 | 2002 | 28 | 20 | 14 | 6 |
| 2003 | 2003 | 28 | 20 | 16 | 4 |
| 2004 | 2004 | 28 | 20 | 16 | 4 |
| 2005 | 2005 | 28 | 20 | 14 | 6 |
| 2006 | 2006 | 28 | 20 | 14 | 6 |
| 2007 | 2007 | 28 | 20 | 13 | 7 |
| 2008 | 2008 | 28 | 20 | 12 | 8 |
| 2009 | 2009 | 28 | 20 | 14 | 6 |
| 2010 | 2010 | 28 | 20 | 16 | 4 |
| 2011 | 2011 | 28 | 20 | 12 | 8 |
| 2012 | 2012 | 28 | 20 | 14 | 6 |
| 2013 | 2013 | 28 | 20 | 16 | 4 |
| 2014 | 2014 | 28 | 20 | 13 | 7 |
| 2015 | 2015 | 28 | 20 | 16 | 4 |
| 2016 | 2016 | 28 | 20 | 16 | 4 |
| 2017 | 2017 | 28 | 20 | 12 | 8 |
| 2018 | 2018 | 28 | 20 | 13 | 7 |
| 2019 | 2019 | 28 | 20 | 16 | 4 |
| 2020 | 2020 | 28 | 20 | 14 | 6 |
| 2021 | 2021 | 28 | 20 | 16 | 4 |
| 2022 | 2022 | 28 | 20 | 14 | 6 |
| 2023 | 2023 | 28 | 20 | 14 | 6 |
| 2024 | 2024 | 28 | 20 | 14 | 6 |
| 2025 | 2025 | 28 | 20 | 16 | 4 |
| 2026 | 2026 | 28 | 20 | 0 | 20 |

## `leaguedashteamstats`

- floor (start year): **1996**
- total files: 868

| season (start) | dir | files | sampled | populated | empty |
|---|---|---|---|---|---|
| **1996** ◀ floor | 1996 | 28 | 20 | 18 | 2 |
| 1997 | 1997 | 28 | 20 | 18 | 2 |
| 1998 | 1998 | 28 | 20 | 18 | 2 |
| 1999 | 1999 | 28 | 20 | 18 | 2 |
| 2000 | 2000 | 28 | 20 | 18 | 2 |
| 2001 | 2001 | 28 | 20 | 18 | 2 |
| 2002 | 2002 | 28 | 20 | 18 | 2 |
| 2003 | 2003 | 28 | 20 | 18 | 2 |
| 2004 | 2004 | 28 | 20 | 18 | 2 |
| 2005 | 2005 | 28 | 20 | 18 | 2 |
| 2006 | 2006 | 28 | 20 | 18 | 2 |
| 2007 | 2007 | 28 | 20 | 18 | 2 |
| 2008 | 2008 | 28 | 20 | 18 | 2 |
| 2009 | 2009 | 28 | 20 | 18 | 2 |
| 2010 | 2010 | 28 | 20 | 18 | 2 |
| 2011 | 2011 | 28 | 20 | 18 | 2 |
| 2012 | 2012 | 28 | 20 | 18 | 2 |
| 2013 | 2013 | 28 | 20 | 18 | 2 |
| 2014 | 2014 | 28 | 20 | 18 | 2 |
| 2015 | 2015 | 28 | 20 | 18 | 2 |
| 2016 | 2016 | 28 | 20 | 18 | 2 |
| 2017 | 2017 | 28 | 20 | 18 | 2 |
| 2018 | 2018 | 28 | 20 | 18 | 2 |
| 2019 | 2019 | 28 | 20 | 18 | 2 |
| 2020 | 2020 | 28 | 20 | 18 | 2 |
| 2021 | 2021 | 28 | 20 | 18 | 2 |
| 2022 | 2022 | 28 | 20 | 18 | 2 |
| 2023 | 2023 | 28 | 20 | 18 | 2 |
| 2024 | 2024 | 28 | 20 | 18 | 2 |
| 2025 | 2025 | 28 | 20 | 18 | 2 |
| 2026 | 2026 | 28 | 20 | 0 | 20 |

## `leaguedashlineups`

- floor (start year): **2007**
- total files: 868

| season (start) | dir | files | sampled | populated | empty |
|---|---|---|---|---|---|
| 1996 | 1996 | 28 | 20 | 0 | 20 |
| 1997 | 1997 | 28 | 20 | 0 | 20 |
| 1998 | 1998 | 28 | 20 | 0 | 20 |
| 1999 | 1999 | 28 | 20 | 0 | 20 |
| 2000 | 2000 | 28 | 20 | 0 | 20 |
| 2001 | 2001 | 28 | 20 | 0 | 20 |
| 2002 | 2002 | 28 | 20 | 0 | 20 |
| 2003 | 2003 | 28 | 20 | 0 | 20 |
| 2004 | 2004 | 28 | 20 | 0 | 20 |
| 2005 | 2005 | 28 | 20 | 0 | 20 |
| 2006 | 2006 | 28 | 20 | 0 | 20 |
| **2007** ◀ floor | 2007 | 28 | 20 | 20 | 0 |
| 2008 | 2008 | 28 | 20 | 20 | 0 |
| 2009 | 2009 | 28 | 20 | 20 | 0 |
| 2010 | 2010 | 28 | 20 | 20 | 0 |
| 2011 | 2011 | 28 | 20 | 20 | 0 |
| 2012 | 2012 | 28 | 20 | 20 | 0 |
| 2013 | 2013 | 28 | 20 | 20 | 0 |
| 2014 | 2014 | 28 | 20 | 20 | 0 |
| 2015 | 2015 | 28 | 20 | 20 | 0 |
| 2016 | 2016 | 28 | 20 | 20 | 0 |
| 2017 | 2017 | 28 | 20 | 20 | 0 |
| 2018 | 2018 | 28 | 20 | 20 | 0 |
| 2019 | 2019 | 28 | 20 | 20 | 0 |
| 2020 | 2020 | 28 | 20 | 20 | 0 |
| 2021 | 2021 | 28 | 20 | 20 | 0 |
| 2022 | 2022 | 28 | 20 | 20 | 0 |
| 2023 | 2023 | 28 | 20 | 20 | 0 |
| 2024 | 2024 | 28 | 20 | 20 | 0 |
| 2025 | 2025 | 28 | 20 | 20 | 0 |
| 2026 | 2026 | 28 | 20 | 0 | 20 |

## `commonteamroster`

- floor (start year): **1996**
- total files: 879

| season (start) | dir | files | sampled | populated | empty |
|---|---|---|---|---|---|
| **1996** ◀ floor | 1996 | 29 | 20 | 20 | 0 |
| 1997 | 1997 | 29 | 20 | 20 | 0 |
| 1998 | 1998 | 29 | 20 | 20 | 0 |
| 1999 | 1999 | 29 | 20 | 20 | 0 |
| 2000 | 2000 | 29 | 20 | 20 | 0 |
| 2001 | 2001 | 29 | 20 | 20 | 0 |
| 2002 | 2002 | 29 | 20 | 20 | 0 |
| 2003 | 2003 | 29 | 20 | 20 | 0 |
| 2004 | 2004 | 30 | 20 | 20 | 0 |
| 2005 | 2005 | 30 | 20 | 20 | 0 |
| 2006 | 2006 | 30 | 20 | 20 | 0 |
| 2007 | 2007 | 30 | 20 | 20 | 0 |
| 2008 | 2008 | 30 | 20 | 20 | 0 |
| 2009 | 2009 | 30 | 20 | 20 | 0 |
| 2010 | 2010 | 30 | 20 | 20 | 0 |
| 2011 | 2011 | 30 | 20 | 20 | 0 |
| 2012 | 2012 | 30 | 20 | 20 | 0 |
| 2013 | 2013 | 30 | 20 | 20 | 0 |
| 2014 | 2014 | 30 | 20 | 20 | 0 |
| 2015 | 2015 | 30 | 20 | 20 | 0 |
| 2016 | 2016 | 30 | 20 | 20 | 0 |
| 2017 | 2017 | 30 | 20 | 20 | 0 |
| 2018 | 2018 | 28 | 20 | 20 | 0 |
| 2019 | 2019 | 28 | 20 | 20 | 0 |
| 2020 | 2020 | 29 | 20 | 20 | 0 |
| 2021 | 2021 | 29 | 20 | 20 | 0 |
| 2022 | 2022 | 28 | 20 | 20 | 0 |
| 2023 | 2023 | 29 | 20 | 20 | 0 |
| 2024 | 2024 | 28 | 20 | 20 | 0 |
| 2025 | 2025 | 28 | 20 | 20 | 0 |
| 2026 | 2026 | 0 | 0 | 0 | 0 |

## `leaguegamelog`

- floor (start year): **1996**
- total files: 62

| season (start) | dir | files | sampled | populated | empty |
|---|---|---|---|---|---|
| **1996** ◀ floor | 1996 | 2 | 2 | 2 | 0 |
| 1997 | 1997 | 2 | 2 | 2 | 0 |
| 1998 | 1998 | 2 | 2 | 2 | 0 |
| 1999 | 1999 | 2 | 2 | 2 | 0 |
| 2000 | 2000 | 2 | 2 | 2 | 0 |
| 2001 | 2001 | 2 | 2 | 2 | 0 |
| 2002 | 2002 | 2 | 2 | 2 | 0 |
| 2003 | 2003 | 2 | 2 | 2 | 0 |
| 2004 | 2004 | 2 | 2 | 2 | 0 |
| 2005 | 2005 | 2 | 2 | 2 | 0 |
| 2006 | 2006 | 2 | 2 | 2 | 0 |
| 2007 | 2007 | 2 | 2 | 2 | 0 |
| 2008 | 2008 | 2 | 2 | 2 | 0 |
| 2009 | 2009 | 2 | 2 | 2 | 0 |
| 2010 | 2010 | 2 | 2 | 2 | 0 |
| 2011 | 2011 | 2 | 2 | 2 | 0 |
| 2012 | 2012 | 2 | 2 | 2 | 0 |
| 2013 | 2013 | 2 | 2 | 2 | 0 |
| 2014 | 2014 | 2 | 2 | 2 | 0 |
| 2015 | 2015 | 2 | 2 | 2 | 0 |
| 2016 | 2016 | 2 | 2 | 2 | 0 |
| 2017 | 2017 | 2 | 2 | 2 | 0 |
| 2018 | 2018 | 2 | 2 | 2 | 0 |
| 2019 | 2019 | 2 | 2 | 2 | 0 |
| 2020 | 2020 | 2 | 2 | 2 | 0 |
| 2021 | 2021 | 2 | 2 | 2 | 0 |
| 2022 | 2022 | 2 | 2 | 2 | 0 |
| 2023 | 2023 | 2 | 2 | 2 | 0 |
| 2024 | 2024 | 2 | 2 | 2 | 0 |
| 2025 | 2025 | 2 | 2 | 2 | 0 |
| 2026 | 2026 | 2 | 2 | 0 | 2 |

## `drafthistory`

- floor (start year): **NONE**
- total files: 0

| season (start) | dir | files | sampled | populated | empty |
|---|---|---|---|---|---|
| 1996 | 1996 | 0 | 0 | 0 | 0 |
| 1997 | 1997 | 0 | 0 | 0 | 0 |
| 1998 | 1998 | 0 | 0 | 0 | 0 |
| 1999 | 1999 | 0 | 0 | 0 | 0 |
| 2000 | 2000 | 0 | 0 | 0 | 0 |
| 2001 | 2001 | 0 | 0 | 0 | 0 |
| 2002 | 2002 | 0 | 0 | 0 | 0 |
| 2003 | 2003 | 0 | 0 | 0 | 0 |
| 2004 | 2004 | 0 | 0 | 0 | 0 |
| 2005 | 2005 | 0 | 0 | 0 | 0 |
| 2006 | 2006 | 0 | 0 | 0 | 0 |
| 2007 | 2007 | 0 | 0 | 0 | 0 |
| 2008 | 2008 | 0 | 0 | 0 | 0 |
| 2009 | 2009 | 0 | 0 | 0 | 0 |
| 2010 | 2010 | 0 | 0 | 0 | 0 |
| 2011 | 2011 | 0 | 0 | 0 | 0 |
| 2012 | 2012 | 0 | 0 | 0 | 0 |
| 2013 | 2013 | 0 | 0 | 0 | 0 |
| 2014 | 2014 | 0 | 0 | 0 | 0 |
| 2015 | 2015 | 0 | 0 | 0 | 0 |
| 2016 | 2016 | 0 | 0 | 0 | 0 |
| 2017 | 2017 | 0 | 0 | 0 | 0 |
| 2018 | 2018 | 0 | 0 | 0 | 0 |
| 2019 | 2019 | 0 | 0 | 0 | 0 |
| 2020 | 2020 | 0 | 0 | 0 | 0 |
| 2021 | 2021 | 0 | 0 | 0 | 0 |
| 2022 | 2022 | 0 | 0 | 0 | 0 |
| 2023 | 2023 | 0 | 0 | 0 | 0 |
| 2024 | 2024 | 0 | 0 | 0 | 0 |
| 2025 | 2025 | 0 | 0 | 0 | 0 |
| 2026 | 2026 | 0 | 0 | 0 | 0 |

