# NBA season start-year → end-year migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the NBA "season" integer mean the **end year** everywhere in the Python code — `compile_nba_season(2024)` = the 2023-24 season, and every Python-published `season` column = 2024 for 2023-24 — matching the NBA/Basketball-Reference convention the ESPN half of the codebase already uses.

**Architecture:** This is a *convergence*, not an invention: `nba_clutch`, `nba_tracking_value`, `leaguedash`, and all ESPN-sourced loaders are already end-year. We flip only the start-year holdouts (`year_to_season`, `compile_nba_season`, `nba_availability`, and the hoopR-side `nba_model_publish` / `nba_data_build`). The migration is breaking for `compile_nba_season`'s public input, so sportsdataverse-py gets a version bump + `BREAKING CHANGE` changelog, and the two Python-produced releases (`nba_stats_rapm`, `nba_stats_possessions`) are re-published end-year. The R package `hoopR` and all `.R` files are **out of scope**.

**Tech Stack:** Python 3.13, polars 1.x, uv, pytest. Two repos: `sportsdataverse-py` (the SDK) and `hoopR-nba-stats-data/python`.

## Global Constraints

- **The season integer means END year after this migration.** `2024` = the 2023-24 season, everywhere in Python. Full-span strings (`"2023-24"`) are unaffected.
- **NEVER double-shift an already-end-year site.** These are ALREADY end-year and must NOT be touched: `nba_clutch.py`, `nba_tracking_value.py` (6 sites), `nba_team_ratings.py`, `nba_oracle_data.py` (external passthrough), `nba_data_build/leaguedash_cli.py`, `nba_data_build/scrape/leaguedash.py`, and all ESPN-sourced `load_nba_*` loaders. When in doubt, read the module's `_season_str`/docstring: if it already says "end year" or does `f"{season-1}-..."`, LEAVE IT.
- **DARKO-safe rule:** flip only at WRITE sites (the final `.alias("season")` and the output filename). Introduce a local `season_end = season + 1`; leave the loop variable, `_season_str(season)`, the DARKO panel tags, and any `last_season == season` join in start-year. Internal `+1` join-shifts (e.g. `nba_availability.py:92`) are convention-agnostic — do NOT touch them.
- **The R package hoopR and all `.R` files are out of scope.** So is `load_nba_stats_schedules` (it reads R-produced span-named files).
- **The commit-subject format `NBA Stats Update (Start: YYYY End: YYYY)` is load-bearing** — a downstream trigger parses it. Do not alter commit-message templates in `pipeline_cli.py` as part of this work.
- No AI co-author trailers (both repos hard-block them). sportsdataverse-py uses Conventional Commits with `type!:` / `BREAKING CHANGE:` for breaking changes.
- Run pytest from each repo's root (`sportsdataverse-py/` or `hoopR-nba-stats-data/python/`).

---

## PR A — sportsdataverse-py SDK (BREAKING)

Work on branch `feat/nba-season-end-year` in `/mnt/sdv_repos/sportsdataverse-py`.

### Task 1: Flip `year_to_season` to take the END year

`year_to_season`'s own summary docstring already claims "season-end year (e.g. 2024)", but its body takes the start year (`year_to_season(2023) -> "2023-24"`). Make the body match the (correct) end-year summary. This is the root of the cascade.

**Files:**
- Modify: `sportsdataverse/nba/nba_schedule.py:271-304`
- Test: `tests/nba/test_nba_schedule.py` (create the test fn if absent)

**Interfaces:**
- Produces: `year_to_season(end_year: int) -> str` — `year_to_season(2024)` returns `"2023-24"`, `year_to_season(2000)` returns `"1999-00"`.

- [ ] **Step 1: Write the failing test**

```python
def test_year_to_season_takes_end_year():
    from sportsdataverse.nba import year_to_season
    assert year_to_season(2024) == "2023-24"   # end year -> span
    assert year_to_season(1997) == "1996-97"
    assert year_to_season(2000) == "1999-00"   # century rollover
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nba/test_nba_schedule.py -k year_to_season_takes_end -v`
Expected: FAIL — currently `year_to_season(2024)` returns `"2024-25"`.

- [ ] **Step 3: Implement**

Replace the body of `year_to_season` (`nba_schedule.py:271-304`):

```python
def year_to_season(year):
    """Convert a season-END year (e.g. 2024) to the NBA's hyphenated label
    (e.g. ``"2023-24"``).

    Args:
        year (int): The ENDING calendar year of the season (2024 for the
            2023-24 season). Matches the NBA/Basketball-Reference convention
            and ``most_recent_nba_season()``.

    Returns:
        str: NBA-style season label, e.g. ``"2023-24"``.

    Example:
        Quick start::

            from sportsdataverse.nba import year_to_season
            print(year_to_season(2024))  # "2023-24"
            print(year_to_season(2000))  # "1999-00"  (century rollover)
    """
    start = year - 1
    return f"{start}-{year % 100:02d}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nba/test_nba_schedule.py -k year_to_season -v`
Expected: PASS. Also run the whole file: `uv run pytest tests/nba/test_nba_schedule.py -v` — fix any sibling test that passed a start year to `year_to_season` (update it to pass the end year).

- [ ] **Step 5: Commit**

```bash
cd /mnt/sdv_repos/sportsdataverse-py
git add sportsdataverse/nba/nba_schedule.py tests/nba/test_nba_schedule.py
git commit -m "refactor(nba)!: year_to_season takes the season END year

BREAKING CHANGE: year_to_season(2024) now returns \"2023-24\" (end-year
input), matching most_recent_nba_season() and the ESPN-sourced loaders.
Previously it took the start year."
```

### Task 2: Flip `compile_nba_season` / `_season_game_index` input to end-year

**Files:**
- Modify: `sportsdataverse/nba/nba_season_compile.py` (`_season_game_index` ~line 36-58, `compile_nba_season` docstrings, the output at line 239 needs NO numeric change)
- Test: `tests/nba/test_nba_season_compile.py:55`

**Interfaces:**
- Consumes: `year_to_season(end_year)` from Task 1.
- Produces: `compile_nba_season(season=<end_year>, ...)` — `compile_nba_season(2024)` compiles the 2023-24 season and tags `season=2024`. `_season_game_index(season=<end_year>, ...)`.

- [ ] **Step 1: Update the failing test**

```python
# tests/nba/test_nba_season_compile.py — test_compile_dedups_gameids_and_tags_season
# The stub _season_game_index is monkeypatched, so this asserts the OUTPUT tag.
# Change the compile call + expectation to end-year:
out = C.compile_nba_season(2024, cache_dir=str(tmp_path), delay_s=0.0)
...
assert out["season"].unique().to_list() == [2024]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/nba/test_nba_season_compile.py::test_compile_dedups_gameids_and_tags_season -v`
Expected: FAIL — output tags `2024` but the assertion (pre-edit) or the call changed; confirm it fails for the right reason (the tag echoes the input, so with input 2024 it should already be 2024 — the REAL change is Step 3 making `_season_game_index` pass the end year to `year_to_season`).

- [ ] **Step 3: Implement**

`_season_game_index` already calls `year_to_season(season)` at `nba_season_compile.py:58`. Because `year_to_season` now takes the END year (Task 1), passing the (now end-year) `season` straight through is **correct with no arithmetic change**. The only work here is documentation: update every docstring/example in `nba_season_compile.py` (lines ~44-45, 103-124, 148, 152-153, 164-181) from "season start year (e.g. 2023 for 2023-24)" to "season END year (e.g. 2024 for 2023-24)". The `pl.lit(season).alias("season")` at line 239 needs no change — it echoes the (now end-year) input.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/nba/test_nba_season_compile.py -v`
Expected: PASS (all tests in the file — the other stubs assert structure, not season direction).

- [ ] **Step 5: Commit**

```bash
git add sportsdataverse/nba/nba_season_compile.py tests/nba/test_nba_season_compile.py
git commit -m "refactor(nba)!: compile_nba_season takes the season END year

BREAKING CHANGE: compile_nba_season(2024) now compiles the 2023-24 season
(was compile_nba_season(2023)). The output season column is now the end year."
```

### Task 3: Flip `nba_availability` output to end-year

**Files:**
- Modify: `sportsdataverse/nba/nba_availability.py` (docstring ~163, output aliases at 219 and 242; leave line 92 and the loop variable)
- Test: `tests/nba/test_nba_availability.py`

**Interfaces:**
- Produces: `nba_availability(seasons=<end_year or list>, ...)` — output `season` column is the end year. Internal `start_year` loop variable stays start-year.

- [ ] **Step 1: Write the failing test**

```python
def test_nba_availability_tags_end_year(monkeypatch):
    import sportsdataverse.nba.nba_availability as A
    # stub the network fetch so the test is offline; assert the season TAG is end-year
    # (build minimal fake leaguedash frames per the module's existing test fixtures)
    out = A.nba_availability(2024, fetch=<stub returning one player-row for 2023-24>)
    assert out["season"].unique().to_list() == [2024]
```
(Model the stub on the existing `test_nba_availability.py` fixtures; the point is the output tag equals the end-year input.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/nba/test_nba_availability.py -k tags_end_year -v`
Expected: FAIL — currently tags `start_year` (2023 for input 2024 under old semantics, or mismatched).

- [ ] **Step 3: Implement**

In `nba_availability.py`, the public `seasons` param becomes end-year. Internally keep the start-year loop for building the stats.nba.com string, and tag the output with end-year:

```python
# ~line 196-197: the loop still needs the START year to build the API string.
# Derive it from the (now end-year) public input:
for end_year in <end-year season list>:
    start_year = end_year - 1
    season_str = f"{start_year}-{str(end_year)[-2:]}"   # 2024 -> "2023-24"
    ...
    # line 219 (and 242 for the G-League bridge): tag END year, not start_year
    ...pl.lit(end_year).cast(pl.Int64).alias("season")...
```
Leave `nba_availability.py:92` (`(pl.col("season") + 1)`) untouched — it's a convention-agnostic next-season join. Update the docstring at ~163 from "start year, e.g. 2019" to "end year, e.g. 2020".

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/nba/test_nba_availability.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sportsdataverse/nba/nba_availability.py tests/nba/test_nba_availability.py
git commit -m "refactor(nba)!: nba_availability seasons + output are end-year

BREAKING CHANGE: the seasons arg and the output season column are now the
end year (2024 = 2023-24)."
```

### Task 4: Loader docstrings + version bump + CHANGELOG

**Files:**
- Modify: `sportsdataverse/nba/nba_loaders.py` (`load_nba_player_impact` docstring ~1015-1057, `load_nba_stats_schedules` note)
- Modify: `pyproject.toml:8` (version), `CHANGELOG.md` (Unreleased section)

**Interfaces:**
- Consumes: nothing. Documentation + release metadata only.

- [ ] **Step 1: Update docstrings**

In `nba_loaders.py`, `load_nba_player_impact`'s docstring: state that `season` is the END year (2024 = 2023-24). Add a one-line note to `load_nba_stats_schedules` that its `seasons` arg is the season start year in span form (`schedule_{season}-YY`) and is unaffected by this migration (R-produced).

- [ ] **Step 2: Bump version + CHANGELOG**

`pyproject.toml`: `version = "0.0.71"` → `"0.0.72"`. In `CHANGELOG.md`'s `## Unreleased`:

```markdown
### BREAKING CHANGES
- **NBA season convention is now END-year across the Python API.**
  `compile_nba_season(2024)`, `year_to_season(2024)`, and `nba_availability`
  now use the season ENDING year (2024 = 2023-24), matching
  `most_recent_nba_season()` and every ESPN-sourced `load_nba_*` dataset.
  Previously the stats.nba.com compile path used the start year. External
  callers passing a start year must add 1. (`nba_box_logs` is unchanged — it
  already takes the hyphenated `"2023-24"` string, not an integer.)
```

- [ ] **Step 3: Regenerate docs (drift gate)**

Run: `uv run python tools/codegen/generate.py --docs && uv run python tools/codegen/generate.py --check`
Expected: exit 0. Revert any `755→644` mode-only churn on `docs/docs/*/index.md`; commit only real content changes.

- [ ] **Step 4: Full NBA suite**

Run: `uv run pytest tests/nba/ -q`
Expected: PASS (the already-end-year modules — clutch, tracking_value, team_ratings — must stay green, proving no double-shift).

- [ ] **Step 5: Commit + open PR**

```bash
git add -A
git commit -m "docs(nba)!: document end-year season convention + bump to 0.0.72

BREAKING CHANGE: see CHANGELOG — NBA season integer is now the end year."
git push -u origin feat/nba-season-end-year
gh pr create --base main --title "refactor(nba)!: NBA season convention -> end year" --body "See CHANGELOG. Flips the start-year holdouts (year_to_season, compile_nba_season, nba_availability) to the end-year convention the ESPN loaders + nba_clutch/nba_tracking_value already use. hoopR R package out of scope."
```

---

## PR B — hoopR-nba-stats-data python

Work on branch `feat/nba-season-end-year` in `/mnt/sdv_repos/hoopR-nba-stats-data`. **Requires PR A merged + the uv.lock bumped to the new SDK** (so `compile_nba_season` end-year semantics are in place). Bump the lock first:
`cd python && uv lock --upgrade-package sportsdataverse`.

### Task 5: `nba_model_publish/builders.py` — end-year output (DARKO-safe)

**Files:**
- Modify: `python/nba_model_publish/builders.py` (write sites 479, 548 filename, 550, model card 235; LEAVE 508, 513, 519)
- Test: `python/tests/test_model_publish_builders.py` (lines 197, 204-205, 233, 258, 292-295)

**Interfaces:**
- Consumes: PR A's end-year `compile_nba_season`.
- Produces: `nba_player_impact_{end_year}.parquet` with `season` = end year; DARKO panel + `last_season` join stay start-year internally.

- [ ] **Step 1: Update the failing tests**

```python
# test_model_publish_builders.py
# :197  assert [r["season"] for r in results] == [2023, 2024]   # was [2022, 2023]
# :233  card["seasons"] == [{"season": 2023, "rows": 3}]        # was 2022
# :292  (tmp_path / "nba_player_impact_2024.parquet").exists()   # was _2023
# Update every asserted season value to end-year (start+1) and every filename.
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd python && uv run pytest tests/test_model_publish_builders.py -v`
Expected: FAIL on the updated assertions (output still start-year).

- [ ] **Step 3: Implement the DARKO-safe flip**

In `build_nba_player_impact`'s loop, after the DARKO join (i.e. after line 519) introduce the end-year label and use it ONLY at write sites:

```python
        season_end = season + 1   # end-year label; internal panel/join stay start-year

        impact = impact.with_columns(
            pl.lit(season_end, dtype=pl.Int64).alias("season"),   # was pl.lit(season) @479
            pl.lit(stype, dtype=pl.Utf8).alias("season_type"),
        )
        ...
        path = out_dir / f"nba_player_impact_{season_end}.parquet"   # was {season} @548
        results.append({"season": season_end, "rows": impact.height, "path": str(path)})  # @550
```
Leave `panel_frames`/`age_frames` tags (508, 513) and `darko.filter(pl.col("last_season") == season)` (519) as `season` (start-year). The model card (`_write_model_card`, line 235) reads `r["season"]` from `results`, which is now `season_end` — no separate change. Update the `season_types`/grain doc text in the card if it names a start year.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_model_publish_builders.py tests/test_model_publish_cli.py -v`
Expected: PASS. Add one assertion that the DARKO projection is unchanged vs a start-year build (the internal panel must not have shifted) — compare `darko_projected_rating` for a fixed player across the flip; it must be identical.

- [ ] **Step 5: Commit**

```bash
cd /mnt/sdv_repos/hoopR-nba-stats-data
git add python/nba_model_publish/builders.py python/tests/test_model_publish_builders.py
git commit -m "refactor(impact)!: nba_player_impact season column + filename are end-year

BREAKING CHANGE: season is now the end year (2024 = 2023-24). DARKO panel and
the last_season join stay start-year internally; only write-time is relabeled."
```

### Task 6: `nba_data_build/build.py` — end-year for the RAPM/possessions family

**Files:**
- Modify: `python/nba_data_build/build.py` (output alias 38, filenames 63-64)
- Test: `python/tests/test_build.py` (37, 40, 46-47)

**Interfaces:**
- Produces: `nba_rapm_{end_year}.parquet`, `nba_possessions_{end_year}.parquet`, with `season` = end year.

- [ ] **Step 1: Update tests**

```python
# test_build.py:37  assert res.season == 2024        # was 2023
# :40  res.rapm["season"].unique().to_list() == [2024]
# :46-47  nba_rapm_2024.parquet / nba_possessions_2024.parquet
```

- [ ] **Step 2: Run to verify fail**

Run: `cd python && uv run pytest tests/test_build.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
    season_end = season + 1
    ratings = nba_rapm(poss).with_columns(pl.lit(season_end, dtype=pl.Int64).alias("season"))  # @38
    ...
    # @63-64 filenames:
    poss.write_parquet(out_dir / f"nba_possessions_{season_end}.parquet")
    ratings.write_parquet(out_dir / f"nba_rapm_{season_end}.parquet")
```
Update the "season start-year" docstrings (31, 52) to end-year. Leave the local per-game cache keyed by start-year (internal, never published).

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_build.py tests/test_publish.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python/nba_data_build/build.py python/tests/test_build.py
git commit -m "refactor(nba-data)!: nba_rapm/possessions season + filenames are end-year

BREAKING CHANGE: season column and filenames now use the end year."
```

### Task 7: Fix the pre-existing `most_recent_nba_season()` off-by-one + reconcile CLI to end-year

**Files:**
- Modify: `python/nba_data_build/cli.py` (19-24 help, 37 default, 34-40 `_resolve_seasons`)
- Modify: `python/nba_data_build/pipeline_cli.py` (86 help, 148 filename; do NOT touch the commit template at 111) and `process/datasets.py` (170-172 filenames)
- Test: `python/tests/` (any test asserting a season default or filename)

**Interfaces:**
- Produces: `--seasons`/`--through` are end-year; `most_recent_nba_season()` (end-year) is now used consistently (no `-1` mismatch).

- [ ] **Step 1: Write the failing test**

```python
def test_resolve_seasons_through_is_end_year_and_matches_most_recent(monkeypatch):
    import nba_data_build.cli as C
    monkeypatch.setattr(C, "most_recent_nba_season", lambda: 2026)  # end year
    # --through defaults to most_recent (end year); last season built == 2026, not 2025
    seasons = C._resolve_seasons(argparse.Namespace(seasons=None, through=None, last_n=1, first=None))
    assert seasons[-1] == 2026
```

- [ ] **Step 2: Run to verify fail**

Run: `cd python && uv run pytest tests/ -k resolve_seasons_through_is_end -v`
Expected: FAIL — today `most_recent_nba_season()` (end-year) is used as a start-year `through`, off by one.

- [ ] **Step 3: Implement**

Now that the whole pipeline is end-year, `most_recent_nba_season()` (already end-year) is the correct default for `--through` with NO adjustment — which also *fixes the pre-existing off-by-one*. Update `cli.py:19-24` help text ("season end-years, e.g. 2024 for 2023-24"), keep `most_recent_nba_season()` as the default (now semantically aligned), and ensure `_resolve_seasons`/`detect_missing_seasons` treat the ints as end-year (the arithmetic is unchanged — only the semantics/labels). Update `pipeline_cli.py:86` help + `:148` filename f-string (`nba_schedule_v3_{season}.parquet` → end-year `season`) and `process/datasets.py:170-172` filename f-strings. **Do NOT edit `pipeline_cli.py:111`** (the `NBA Stats Update (Start:...End:...)` commit template — load-bearing).

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/ -q`
Expected: PASS.

- [ ] **Step 5: Commit + open PR**

```bash
git add -A
git commit -m "fix(nba-data)!: CLI seasons are end-year; fix most_recent_nba_season off-by-one

BREAKING CHANGE: --seasons/--through are the season end year. This also fixes a
pre-existing bug where most_recent_nba_season() (end-year) was fed into a
start-year slot."
git push -u origin feat/nba-season-end-year
gh pr create --base main --title "refactor(nba-data)!: end-year season convention + off-by-one fix" --body "Depends on sportsdataverse-py PR A. Flips nba_model_publish + nba_data_build to end-year; fixes the most_recent_nba_season off-by-one. R side untouched."
```

---

## PR C — re-publish the Python-produced releases end-year

**Requires PR B merged.** Only `nba_stats_rapm` and `nba_stats_possessions` are Python-produced (from `nba_data_build/build.py`); `nba_stats_schedules` is R-produced span-named and out of scope.

### Task 8: Re-run + re-publish end-year

**Files:** none (operational).

- [ ] **Step 1: Re-run the build** (uses the warm possession cache — no re-fetch):

```bash
cd /mnt/sdv_repos/hoopR-nba-stats-data && . ~/.config/sdv/env
SDV_PY_NBA_CACHE_DIR=/data/nba_possessions \
  uv run --project python python -m nba_data_build.cli --seasons 1997:2026
# (end-year args: 1997 = 1996-97 through 2026 = 2025-26)
```

- [ ] **Step 2: Verify filenames are end-year**

```bash
ls python/build_out/**/nba_rapm_*.parquet | head
# expect nba_rapm_1997.parquet ... nba_rapm_2026.parquet (end-year), NOT _1996/_2025
```

- [ ] **Step 3: Re-publish**

```bash
cd python && uv run python -m nba_data_build.cli --publish   # or the repo's upload entry point
gh release view nba_stats_rapm -R sportsdataverse/sportsdataverse-data
```

- [ ] **Step 4: Round-trip check**

```bash
uv run python -c "from sportsdataverse.nba import load_nba_stats_rapm; print(load_nba_stats_rapm(2024).height)"  # 2024 = 2023-24
```

---

## Execution order

PR A (SDK) → merge → bump hoopR lock → PR B (stats-data) → merge → PR C (re-publish). The `nba_player_impact` first publish (separate handoff, `docs/WARM_HANDOFF.md` step 5) must happen AFTER PR B so its output is end-year from day one. The cache warm runs independently throughout.
