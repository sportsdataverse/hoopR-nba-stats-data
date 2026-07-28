# Deferred: build `nba_stats_draft` (Phase 3)

The NBA v3 reshaper (PR #18) shipped **14 of 15** datasets. `nba_stats_draft` is
the lone gap because its source endpoint `drafthistory` has **0 files** in the
raw store and needs a **live stats.nba.com scrape** — which stalls on the droplet's
datacenter IP, so it must run **off-droplet** (dev box / residential IP or a
residential proxy). Everything else is done; this is self-contained.

## Steps (run on the dev box)

1. **Wire the endpoint** in `hoopR-nba-stats-raw`: add `drafthistory` to the
   league-/season-level endpoint set the scraper discovers (see
   `scripts/endpoints.py` `discover()` + the `LEAGUE_*` constants; it is a single
   league-level payload per season, like `franchisehistory`). `LeagueID="00"`.
2. **Capture 1996–2025** via the raw scraper; commit to `main` with the
   load-bearing `NBA Stats Update (Start: YYYY End: YYYY)` subject; push. Use
   `scripts/commit_loop.sh` alongside if it is a long pass.
3. **Build + publish** just the draft dataset (droplet-safe once captured, but
   you'll already be on the dev box):
   ```sh
   cd hoopR-nba-stats-data/python
   .venv/bin/python -m nba_data_build.reshape \
     --root ../../hoopR-nba-stats-raw/nba_stats/json \
     --seasons $(seq 1996 2025) --datasets draft --out /tmp/nba_draft --publish
   ```
   This creates the `nba_stats_draft` tag and ships parquet+rds+csv.
4. **Flip the marker test**: in `python/tests/test_reshape_build.py`,
   `test_draft_is_empty_pending_phase_3_capture` asserts `height == 0` today —
   change it to assert `> 0` for a season with a known draft once captured.

## Everything already done (do NOT redo)
- Reshaper code (`reshape/{raw,datasets,io,build,cli}.py`) + processor: PR #18, 55 tests.
- 14 tags published, full 1996–2025, parquet+rds+csv, `hoopR_data` stamp verified in R.
- `nba_stats_pbpv3` intentionally KEPT (retire later once rebuilt `nba_stats_pbp`
  is verified downstream).
- sdv-orch `data.build_py` stage live (manual-trigger, droplet-safe).
- `drafthistory` is NOT yet in the reshaper's coverage floors — it will just build
  whatever seasons are captured (its `datasets.py` entry has no floor).
