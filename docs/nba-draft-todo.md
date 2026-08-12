# DONE: `nba_stats_draft` (Phase 3) — published 2026-08-12

The NBA v3 reshaper (PR #18) shipped **14 of 15** datasets; `nba_stats_draft`
was the lone gap. It is now published: **30 seasons (1996–2025), 1,773 picks,
90 assets** (parquet + csv + rds).

Kept as a record of what the gap actually was, because the diagnosis in the
original plan was wrong in a way worth not repeating.

## What the blocker really was

The plan assumed `drafthistory` merely needed adding to an endpoint list in
`hoopR-nba-stats-raw`. It did not — that repo's `python/endpoints.py` is a
re-export shim, and the sweep **discovers** season endpoints by introspecting
sdv-py's generated `nba_stats` module. The real chain:

1. sdv-py's canonical catalog marked drafthistory
   `league_applicability["00"] = "barren"`.
2. `gen_nba_stats._stats_eps()` keeps only `"live"`, so `nba_stats_drafthistory`
   was **never generated**.
3. With no wrapper, `discover()` could not see the endpoint, so the NBA sweep
   could never capture it — while the WNBA twin, marked `live`, had been
   capturing it since 1997.

"barren" was a misdiagnosis. Measured 2026-08-12 from a residential IP, with a
`franchisehistory` control in the same session to separate a real zero-row
answer from stats.nba.com's silent hang on datacenter IPs:

| call | result |
|---|---|
| `franchisehistory` LeagueID=00 (control) | 74 rows |
| `drafthistory` LeagueID=00, no season | 8,434 rows, 1947–2026 |
| `drafthistory` LeagueID=00, Season=2003 | 58 rows, #1 LeBron James |
| `drafthistory` LeagueID=15 / =20 | 0 rows (genuinely barren) |

Fixed in sportsdataverse-py **PR #362**, which flips `"00"` only and leaves
Summer League / G-League alone.

## The second bug that PR also fixed

`_SEASON_PARAMS` is matched by **exact** name, and drafthistory is the only
endpoint spelling its season `season_year_nullable` — which does not match
`season_year`. So `season_variants()` emitted no season at all. Unfiltered,
drafthistory returns the FULL history, so this does **not** surface as an empty
capture: it writes the same payload under every season.

`wehoop-wnba-stats-raw` is in exactly that state today — 30 byte-identical
`drafthistory/{season}.json` files, all `md5 b682aa93cc`, each echoing
`"Season": null`. **The WNBA twin still needs a re-capture**; only the NBA side
was fixed here.

## Season keying (differs from every other dataset in this repo)

`drafthistory` keys on the **draft year**, not the end-year season label the
daily job uses: `draft_2003.parquet` is the June 2003 draft, which precedes the
2003-04 season. Verified against the payload (`SEASON` = 2003, #1 = LeBron).

## Done

- Raw capture: `hoopR-nba-stats-raw@0ca0b8ca45`, 30 payloads, each verified as
  a non-empty `DraftHistory` set carrying only its own season before being
  written. All 30 distinct (no repeat of the WNBA failure).
- Published to `nba_stats_draft`: 90 assets, 0 failed, no zero-byte assets.
- D39 model `Draft` declared from the published `draft_2025.parquet`;
  `UNPUBLISHED` is now empty.
- Marker test flipped: `test_draft_builds_from_the_real_store` asserts 60 picks
  for 2013 over rounds [1, 2] — a count, not just non-emptiness, so a season
  that silently lost its filter would still fail.
- `.github/workflows/annual_nba_stats_draft.yml` — late-June cron + a
  second-pass day, diff-ported from the WNBA workflow's April dates.

## Notes

- Entity ids stay **Int64** (`person_id`, `team_id`), matching
  `models.py`'s rule and the repo-wide `test_entity_ids_are_declared_int64`
  gate. Only `game_id` is Utf8 (zero-padded), and draft carries no `game_id`.
- `drafthistory` has no coverage floor in `datasets.py`; it builds whatever
  seasons are captured. 2026 is already available upstream (60 picks) if the
  published range is ever extended.
