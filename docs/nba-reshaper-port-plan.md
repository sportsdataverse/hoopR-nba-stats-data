# NBA Stats v3 reshaper — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans (or subagent-driven-development) to implement this task-by-task. Steps use `- [ ]` checkboxes.

**Goal:** Rebuild every classic `nba_stats_*` release dataset from the unified NBA raw store using Python producers reading the **v3** API endpoints, for the **full 1996–2026** history, replacing the R-era output.

**Architecture:** A new `python/nba_data_build/reshape/` subpackage mirroring the proven WNBA reshaper (`wehoop-wnba-stats-data/python/wnba_data_build/`), adapted for NBA's season convention and the `hoopR_data` stamp. Reuses the repo's existing tag-agnostic `publish.py`. Kept clear of the existing v3-rollup/modeling code (`process/`, `build.py`), which is untouched.

**Tech Stack:** Python 3, polars 1.x, uv, `sportsdataverse._rds.write_rds`, `gh` CLI.

## Decisions locked (from scoping + user)

- **Full replacement, not parity.** The v3 schema is the new contract; matching the old R column set is NOT a goal. Old R content is overwritten.
- **Classic tag names survive**, carrying v3 content. Retire the redundant `nba_stats_pbpv3` (folded into `nba_stats_pbp`). No hoopR SDK loader repoint. `nba_stats_possessions_v3` / `nba_stats_lineups_v3` (no classic twin) are untouched.
- **Draft source = `drafthistory`** (OQ1 resolved) — but it has **0 files** in the store today, so it must be captured in `-raw` first (Phase 3).
- **Full history 1996–2026**, complete rebuild (clobber all seasons), not incremental.

## Global Constraints

- **polars 1.x modern API only** (`group_by`, `with_row_index`, `pl.len()`, `how="full", coalesce=True`; bool masks explicit; no lookaround regex).
- **uv** for everything (`uv run pytest|ruff`); no `pip`/`requirements.txt`. Venv interpreter by absolute path in shell wrappers (systemd PATH lacks `/root/.local/bin`).
- **Season labels use START year** (1996 = 1996-97). **The store dir convention is SPLIT (verified in Phase 0):** game endpoints (playbyplayv3, boxscoresummaryv2, boxscoretraditionalv3) key by **END year** — `dir = season + 1` (game `0021300001` → `/2014/`); the six league endpoints (leaguestandingsv3, leaguedash*, leaguegamelog, commonteamroster, drafthistory) key by **START year** — `dir = season`. Task 1.1 hardcodes exactly this split; there is nothing left to "confirm per endpoint".
- **History range = 1996–2025 start-year** (verified in Phase 0): 2026-27 is unplayed, so a 2026 build yields nothing. `seq 1996 2025`, not 2026.
- **ID/join-key dtype discipline:** one dtype per id at the boundary; assert `left.schema[k] == right.schema[k]` before any join; `game_id` is zero-padded to 10; never a float→Utf8 id cast.
- **RDS stamp** = `("hoopR_data","tbl_df","tbl","data.table","data.frame")` + `hoopR_timestamp` (POSIXct) + `hoopR_type` (per `hoopR/R/utils.R:634`).
- **Commits:** Conventional Commits; branch + PR (this is a code/library repo, not a data repo); **never** an AI co-author trailer. The `-raw` capture in Phase 3 targets `main` directly (data repo) with the load-bearing `NBA Stats Update (Start: YYYY End: YYYY)` subject.
- **Droplet constraint:** the reshaper *build* is droplet-safe (reads committed store, uploads via `gh`). The Phase 3 draft *capture* hits stats.nba.com — **verify it works via the proxy pool before fanning out; it may have to run off-droplet** (CLAUDE.md: stats.nba.com can stall on the datacenter IP).

## Target datasets → tags (15)

Mirrors the WNBA 15. Endpoint = v3 where one exists.

| key | endpoint | resultSet | tag | tag status |
|---|---|---|---|---|
| standings | leaguestandingsv3 | — | nba_stats_standings | NEW |
| player_season_stats | leaguedashplayerstats | — | nba_stats_player_season_stats | NEW¹ |
| team_season_stats | leaguedashteamstats | — | nba_stats_team_season_stats | NEW¹ |
| lineups | leaguedashlineups | — | nba_stats_lineups | NEW² (floor 2007) |
| rosters | commonteamroster | CommonTeamRoster | nba_stats_rosters | NEW |
| coaches | commonteamroster | Coaches | nba_stats_coaches | NEW |
| draft | drafthistory | — | nba_stats_draft | NEW (needs capture) |
| schedules | leaguegamelog | — | nba_stats_schedules | REBUILD |
| player_game_logs | leaguegamelog | — | nba_stats_player_game_logs | NEW |
| pbp | playbyplayv3 | game.actions | nba_stats_pbp | REBUILD (retire pbpv3) |
| game_rosters | boxscoresummaryv2 | InactivePlayers | nba_stats_game_rosters | NEW |
| officials | boxscoresummaryv2 | Officials | nba_stats_officials | NEW |
| player_boxscores | boxscoretraditionalv3 | — | nba_stats_player_boxscores | REBUILD |
| team_boxscores | boxscoretraditionalv3 | — | nba_stats_team_boxscores | REBUILD |
| shots | derived from pbp | — | nba_stats_shots | NEW |

¹ Reconcile against the existing `nba_stats_leaguedash` tag in Task 0.1 — it may already carry a combined form.
² **`nba_stats_lineups` (leaguedash lineups) ≠ `nba_stats_lineups_v3` (on-court possession lineups).** Different datasets; do not conflate or overwrite `_v3`.

---

## Phase 0 — De-risk before writing code

### Task 0.1: Tag manifest (create / rebuild / retire)
**Files:** Create `docs/nba-tag-manifest.md`.
- [ ] Enumerate live `nba_stats_*` tags (`gh release list`) and cross-check against the 15 target tags.
- [ ] Decide per tag: create / rebuild / leave. **RESOLVED in Phase 0:** `nba_stats_leaguedash` is LEFT ALONE — it is a 794-asset combined legacy dump carrying `player_bio`, twelve `player_tracking_*` families, and `*_master` rollups that are NOT in the target 15; folding/deleting would drop live content. Porting those extra families is future work, out of scope here.
- [ ] Record the one retirement: `nba_stats_pbpv3` → delete after `nba_stats_pbp` is rebuilt and verified.
- [ ] Commit the manifest.

### Task 0.2: v3 coverage probe (the "full history" reality check)
**Files:** Create `scripts/probe_v3_coverage.py` (throwaway-OK, but commit it).
- [ ] For each source endpoint, count populated vs empty payloads per season 1996–2026 against the real store (an empty 200 is not coverage — reuse the `classify()` logic from the `-raw` observability module).
- [ ] Output a per-endpoint **season floor** (first season with real data). v3 pbp/box may be sparse or empty in early seasons.
- [ ] **Gate:** if any target endpoint is empty before some year, record that floor in `datasets.py` (Task 1.2) so those datasets simply produce no artifact for pre-floor seasons rather than shipping empty releases. Log the floors; do not silently drop.

---

## Phase 1 — `reshape/` scaffolding

### Task 1.1: `reshape/raw.py` — read layer with the NBA season mapping
**Files:** Create `python/nba_data_build/reshape/raw.py`; Test `python/tests/test_reshape_raw.py`.
**Interfaces produced:** `season_game_ids`, `available_games`, `iter_game_payloads`, `result_set`, `season_payload`, `game_payload_path` — same names WNBA's `build.py` calls.
- [ ] Port `wehoop-wnba-stats-data/python/wnba_data_build/raw.py` verbatim, then change the season↔dir mapping: game-endpoint reads must map a **start-year** season arg to the **end-year** store dir (`store_dir = season + 1`), matching `scrape.raw_store.season_of`. Season-level endpoint dirs: confirm each against the store (Task 0.2 output) and map accordingly.
- [ ] Point `RAW_BASE` at the NBA `-raw` repo raw.githubusercontent URL.
- [ ] **Test:** game `0021300001` with season arg `2013` resolves to `.../playbyplayv3/2014/0021300001.json`; a season-level payload (standings 2013) resolves to its actual stored dir. Assert on the real store (skip if no sibling checkout).

### Task 1.2: `reshape/datasets.py` — registry
**Files:** Create `python/nba_data_build/reshape/datasets.py`; Test `python/tests/test_reshape_datasets.py`.
**Interfaces produced:** `Dataset` NamedTuple (add a `season_floor: int | None` field vs WNBA's), `DATASETS` (15), `BY_KEY`, `RELEASE_TAGS`.
- [ ] Port WNBA `datasets.py`; retarget every `release_tag` to `nba_stats_*`, every `wehoop_type` string to an `nba_type` describing the dataset "… from hoopR data repository", and add the per-endpoint `season_floor` from Task 0.2.
- [ ] **Test:** `len(DATASETS) == 15`; `RELEASE_TAGS` are all `nba_stats_*` and unique; `lineups` tag is `nba_stats_lineups`, NOT `_v3`.

### Task 1.3: `reshape/io.py` — hoopR stamp
**Files:** Create `python/nba_data_build/reshape/io.py`; Test `python/tests/test_reshape_io.py`.
**Interfaces produced:** `write_release_formats(df, dest_dir, stem, nba_type, timestamp) -> dict[str,Path]`; `RDS_CLASS`.
- [ ] Port WNBA `io.py`; set `RDS_CLASS = ("hoopR_data","tbl_df","tbl","data.table","data.frame")` and the attr keys to `hoopR_timestamp` / `hoopR_type`.
- [ ] **Test:** write a 2-row frame; read the rds header back (or assert via `sportsdataverse._rds` round-trip) — class chain and both attrs present.

---

## Phase 2 — builders

### Task 2.1: season-level resultSets builder
**Files:** Create `python/nba_data_build/reshape/build.py` (`build`, `build_season_dataset`, `frame_from_result_set`, `snake`, `_variant_columns`); Test `python/tests/test_reshape_build.py`.
- [ ] Port the season-level half of WNBA `build.py`. Keep `snake()`'s two-pass split (`LeagueID` → `league_id`, never `league_i_d`).
- [ ] **Test:** build `standings` and `player_season_stats` for one real season; assert non-empty, snake_case columns, `season` column = the **start-year** arg.

### Task 2.2: game-level v3 builders
**Files:** Extend `reshape/build.py` (`build_game_dataset`, `build_pbp`, `pbp_rows`, `build_boxscores`, `boxscore_rows`, `_flatten_stats`).
- [ ] Port WNBA's game-level + pbp + boxscore builders unchanged (v3 nesting is identical across leagues). `build_game_dataset` covers `game_rosters`/`officials` (boxscoresummaryv2 resultSets); `build_pbp`/`build_boxscores` cover the v3-nested ones.
- [ ] **Test:** for one real season, `build_pbp` non-empty with `game_id`+`season`; `build_boxscores(team_level=False/True)` both non-empty; `game_rosters` via `build_game_dataset` non-empty.

### Task 2.3: derived shots
**Files:** Extend `reshape/build.py` (`build_shots`, `_SHOT_COLUMNS`).
- [ ] Port `build_shots`; verify the v3 shot fields exist in NBA pbp (same `is_field_goal`/geometry columns) — if a field name differs, adjust `_SHOT_COLUMNS`.
- [ ] **Test:** `build_shots(build_pbp(root, season))` non-empty; every row is a field-goal action.

### Task 2.4: draft builder
**Files:** Extend `reshape/build.py` (draft is season-level once captured).
- [ ] After Phase 3 lands drafthistory, wire `draft` through `build_season_dataset`. **Test:** non-empty for a season with a known draft.

---

## Phase 3 — capture `drafthistory` in `-raw`

### Task 3.1: add drafthistory to the NBA raw scraper
**Files (repo `hoopR-nba-stats-raw`):** Modify `scripts/endpoints.py` (league-level endpoint set); run `scripts/scrape_raw_json.py`.
- [ ] Add `drafthistory` to the league/season-level endpoint list (it is a single league-level payload per season, like `franchisehistory`).
- [ ] **Verify the proxy path reaches stats.nba.com** with one season before fanning out (droplet risk — see Global Constraints). If it stalls, run this capture off-droplet.
- [ ] Capture 1996–2026, commit to `main` with the load-bearing subject, push. Run `commit_loop.sh` alongside if it is a long pass.

---

## Phase 4 — CLI + processor

### Task 4.1: `reshape/cli.py` + `__main__.py`
**Files:** Create `python/nba_data_build/reshape/cli.py`, `python/nba_data_build/reshape/__main__.py`; Test `python/tests/test_reshape_cli.py`.
- [ ] Port WNBA `cli.py`: same `build_dataset` routing (pbp/shots/boxscores special-cased, shots reuses the season's pbp frame), same `--seasons/--datasets/--root/--out/--repo/--publish/--dry-run`. `--root` default = the NBA store json base. Reuse the existing repo `publish.py` (already tag-agnostic).
- [ ] Entry point: `python -m nba_data_build.reshape`.
- [ ] **Test:** port WNBA `test_cli.py` — `_resolve_datasets` order/dedupe/unknown-key; shots reuses pbp without a rebuild; boxscores route to team/player levels.

### Task 4.2: processor wrapper
**Files:** Create `scripts/daily_nba_stats_python_processor.sh`.
- [ ] Port `wehoop-wnba-stats-data/scripts/daily_wnba_stats_python_processor.sh`: `-s/-e`, venv python by absolute path, preflight on the `-raw` sibling, temp `--out`, `--publish`, PIPESTATUS exit recovery. Env `HOOPR_NBA_STATS_RAW_ROOT` → `${SDV_REPOS}/hoopR-nba-stats-raw/nba_stats/json`.
- [ ] **Test:** stub PYBIN to echo; confirm per-season command + preflight fast-fail.

---

## Phase 5 — full-history rebuild + publish

### Task 5.1: local full build (dry-run)
- [ ] `python -m nba_data_build.reshape --root <store> --seasons $(seq 1996 2025) --out <tmp> --dry-run` (2026-27 unplayed — see Global Constraints).
- [ ] Cross-check per-dataset season coverage against the Task 0.2 floors; confirm no season below a floor produced an artifact, and every season above it did. Record row counts.

### Task 5.2: publish (create / rebuild / retire)
- [ ] Re-run with `--publish` (creates the 11 new tags, clobbers all seasons on the 4 rebuilt tags). `upload_artifacts` already `--clobber`s and creates missing releases.
- [ ] After `nba_stats_pbp` is verified, **retire `nba_stats_pbpv3`** (`gh release delete`, per the Task 0.1 manifest).

### Task 5.3: verify releases
- [ ] For 3 spot tags (pbp, standings, shots): asset count = seasons×3 formats; download one rds and load it (R `readRDS` or `sportsdataverse._rds` round-trip) — confirm the `hoopR_data` class + stamp survived the round trip.

---

## Phase 6 — cutover + docs

### Task 6.1: sdv-orch `data.build_py` stage
**Files (repo `sdv-orch`):** Modify `sdv_orch/registry.py` (`nba_stats` pipeline).
- [ ] Add a droplet-safe `data.build_py` stage mirroring the WNBA one (`d3b4cda`): `scripts/daily_nba_stats_python_processor.sh`, `ArgStyle.FLAG_SE`, empty `rate_classes`, `env` HOOPR_NBA_STATS_RAW_ROOT, not in `default_stages`, no cron.
- [ ] **Confirm with the user before editing** (config/system-touching). Then `systemctl restart sdv-orch-flows.service`; verify active; commit locally.

### Task 6.2: fix stale docs
**Files:** Modify `hoopR-nba-stats-data/.github/copilot-instructions.md`, `CLAUDE.md`; and the WNBA repo's copilot-instructions ("There is no wehoop-wnba-stats-raw" is now false).
- [ ] Correct the "raw layer" descriptions to reflect the new `-raw` store + Python reshaper. Note the retained R scrapers are the capture path, the Python reshaper is the build+publish path.

---

## Self-review notes

- **Spec coverage:** all 15 datasets have a build task; draft has its capture prerequisite (Phase 3); full-history + retire + cutover + docs covered.
- **Highest risks, front-loaded:** season start↔end mapping (Task 1.1 test), v3 early-season coverage (Task 0.2 gate), draft capture reaching stats.nba.com from the droplet (Task 3.1 verify-first).
- **DRY:** the bulk is "port WNBA module, apply named diffs" — the WNBA reshaper is the proven reference; this plan does not re-derive the extractors.
- **YAGNI:** no incremental-detection (`incremental.py`) — this is an explicit full rebuild; add it only if daily runs later need it.
```
