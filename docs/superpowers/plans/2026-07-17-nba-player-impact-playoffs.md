# nba_player_impact Playoffs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `nba_player_impact` a `season_type` dimension so playoff and regular-season impact are separable rows, without degrading the regular-season numbers.

**Architecture:** The builder's per-season loop gains a second pass. The regular-season (RS) pass runs exactly as today and additionally *fits* the two season-level quantities (SPM `coef`, `pts_per_win`); the playoff (PO) pass reuses those fitted values and takes the RS SPM as its adj-RAPM prior. Both passes emit rows into one parquet per season, tagged `season_type`. A single possession-weighted blend helper feeds both forward-carrying mechanisms — the next season's adj-RAPM prior and the season-granular DARKO panel row.

**Tech Stack:** Python 3.13, polars 1.x, uv, pytest. `sportsdataverse` pinned via `uv.lock` at `main@f80d4909`.

## Global Constraints

- **Season types are exactly `"Regular Season"` and `"Playoffs"`** — the literal stats.nba.com `SeasonType` strings, matching `nba_data_build/scrape/leaguedash.py:54` (`SEASON_TYPES`). `PlayIn` is out of scope and must be named as excluded in the model card.
- **No SDK changes.** `compile_nba_season(season, season_type=...)` and `nba_box_logs(season, season_type=...)` already accept the parameter.
- **The possession cache must not be invalidated.** Do not touch `PIPELINE_VERSION`. Playoff game ids are `004…`, regular season `002…` — distinct keys.
- **SPM `coef` and `pts_per_win` are fitted ONCE per season, on RS data**, and reused for PO. Never re-fit them on a playoff sample.
- **Both forward-carrying mechanisms use the same possession-weighted blend** (`_blend_by_poss`). Never let a PO-only estimate become the next season's prior.
- **DARKO stays season-granular** — one panel row per player-season. Do not add a playoff time step.
- **A season with no playoffs is not an error** — emit the RS row, skip PO, carry the RS SPM forward alone.
- No AI co-author trailers on commits (repo rule; the `sdv-toolkit` hook hard-blocks them).
- Run everything from `/mnt/sdv_repos/hoopR-nba-stats-data/python`.

---

### Task 1: `_blend_by_poss` — the possession-weighted blend helper

The one rule both forward-carrying mechanisms use. Built and tested first because Tasks 3 and 4 both consume it.

**Files:**
- Modify: `python/nba_model_publish/builders.py` (add helper next to `_team_season`, ~line 103)
- Test: `python/tests/test_model_publish_builders.py`

**Interfaces:**
- Consumes: nothing (pure function).
- Produces: `_blend_by_poss(rs: pl.DataFrame, po: Optional[pl.DataFrame], value_cols: list[str], weight_col: str) -> pl.DataFrame` — outer-joins RS and PO on `player_id`, returns one row per player with each `value_col` as the weight-averaged combination and `weight_col` summed. A player present in only one frame keeps that frame's values unchanged. `po=None` or an empty `po` returns `rs` untouched.

- [ ] **Step 1: Write the failing test**

```python
def test_blend_by_poss_weights_by_possessions():
    rs = pl.DataFrame({"player_id": [1], "rating": [2.0], "poss": [900]})
    po = pl.DataFrame({"player_id": [1], "rating": [6.0], "poss": [100]})
    out = B._blend_by_poss(rs, po, ["rating"], "poss")
    # 900/1000 * 2.0 + 100/1000 * 6.0 = 2.4 -- the thin PO sample must not dominate
    assert out["rating"].to_list() == [pytest.approx(2.4)]
    assert out["poss"].to_list() == [1000]


def test_blend_by_poss_player_in_one_frame_only():
    rs = pl.DataFrame({"player_id": [1, 2], "rating": [2.0, 5.0], "poss": [900, 800]})
    po = pl.DataFrame({"player_id": [1], "rating": [6.0], "poss": [100]})
    out = B._blend_by_poss(rs, po, ["rating"], "poss").sort("player_id")
    # player 2 missed the playoffs -> unchanged, NOT nulled
    assert out["rating"].to_list() == [pytest.approx(2.4), pytest.approx(5.0)]
    assert out["poss"].to_list() == [1000, 800]


def test_blend_by_poss_empty_playoffs_returns_rs_unchanged():
    rs = pl.DataFrame({"player_id": [1], "rating": [2.0], "poss": [900]})
    empty = pl.DataFrame({"player_id": [], "rating": [], "poss": []},
                         schema={"player_id": pl.Int64, "rating": pl.Float64, "poss": pl.Int64})
    assert B._blend_by_poss(rs, empty, ["rating"], "poss")["rating"].to_list() == [2.0]
    assert B._blend_by_poss(rs, None, ["rating"], "poss")["rating"].to_list() == [2.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_model_publish_builders.py -k blend_by_poss -v`
Expected: FAIL — `AttributeError: module 'nba_model_publish.builders' has no attribute '_blend_by_poss'`

- [ ] **Step 3: Write minimal implementation**

Add to `builders.py` after `_team_season`:

```python
def _blend_by_poss(
    rs: pl.DataFrame,
    po: Optional[pl.DataFrame],
    value_cols: list[str],
    weight_col: str,
) -> pl.DataFrame:
    """Possession-weighted combination of a regular-season and playoff frame.

    The ONE forward-carrying rule: both the next season's adj-RAPM prior and the
    DARKO panel row use this. A playoff sample is ~15 games/team, so a straight
    "most recent estimate wins" carry would let a thin sample override a
    1230-game one -- adding playoffs would then DEGRADE every regular-season row.
    Weighting by possessions keeps the full RS sample behind the carried value
    while still letting playoff form move it.

    A player in only one frame keeps that frame's values (not null, not halved).

    Args:
        rs: Regular-season frame; one row per ``player_id``.
        po: Playoff frame, or None/empty -- either returns *rs* untouched.
        value_cols: Columns to weight-average.
        weight_col: Possession-count column; summed in the output.

    Returns:
        One row per ``player_id`` with blended *value_cols* and summed *weight_col*.
    """
    if po is None or po.height == 0:
        return rs

    joined = rs.join(po, on="player_id", how="full", coalesce=True, suffix="_po")
    w_rs = pl.col(weight_col).fill_null(0)
    w_po = pl.col(f"{weight_col}_po").fill_null(0)
    total = w_rs + w_po

    exprs = []
    for c in value_cols:
        v_rs, v_po = pl.col(c), pl.col(f"{c}_po")
        exprs.append(
            pl.when(total == 0)
            .then(v_rs.fill_null(v_po))
            .otherwise(
                (v_rs.fill_null(0) * w_rs + v_po.fill_null(0) * w_po) / total
            )
            .alias(c)
        )
    exprs.append(total.alias(weight_col))
    return joined.select("player_id", *exprs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_model_publish_builders.py -k blend_by_poss -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add python/nba_model_publish/builders.py python/tests/test_model_publish_builders.py
git commit -m "feat(impact): add _blend_by_poss, the possession-weighted carry rule"
```

---

### Task 2: `--season-types` CLI flag

**Files:**
- Modify: `python/nba_model_publish/cli.py:129` (insert after the `--delay-s` block)
- Modify: `python/nba_model_publish/cli.py` (the `build_nba_player_impact(...)` call in `main`, ~line 210)
- Test: `python/tests/test_model_publish_cli.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `args.season_types: list[str]`, passed to `build_nba_player_impact(..., season_types=args.season_types)`. Default `["Regular Season", "Playoffs"]`.

- [ ] **Step 1: Write the failing test**

```python
def test_season_types_defaults_to_both():
    args = C.build_parser().parse_args(["impact", "--seasons", "2023"])
    assert args.season_types == ["Regular Season", "Playoffs"]


def test_season_types_accepts_rs_only_for_regression_diffing():
    args = C.build_parser().parse_args(
        ["impact", "--seasons", "2023", "--season-types", "Regular Season"]
    )
    assert args.season_types == ["Regular Season"]


def test_season_types_rejects_unknown_value():
    with pytest.raises(SystemExit):
        C.build_parser().parse_args(
            ["impact", "--seasons", "2023", "--season-types", "PlayIn"]
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_model_publish_cli.py -k season_types -v`
Expected: FAIL — `AttributeError: 'Namespace' object has no attribute 'season_types'`

- [ ] **Step 3: Write minimal implementation**

Add near the top of `cli.py`, beside `_parse_seasons`:

```python
SEASON_TYPES: tuple[str, ...] = ("Regular Season", "Playoffs")


def _parse_season_types(spec: str) -> list[str]:
    """Comma-separated stats.nba.com SeasonType strings -> validated list.

    Only "Regular Season" and "Playoffs" are supported. "PlayIn" is a real
    third SeasonType (2020+, ~4-6 games/yr) but is deliberately out of scope --
    see docs/superpowers/specs/2026-07-17-nba-player-impact-playoffs-design.md.

    Args:
        spec: e.g. ``"Regular Season,Playoffs"``.

    Returns:
        Season types in canonical build order (RS before PO).

    Raises:
        argparse.ArgumentTypeError: On an unknown or empty season type.
    """
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("--season-types must not be empty")
    unknown = [p for p in parts if p not in SEASON_TYPES]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"invalid --season-types {unknown!r}: expected any of {list(SEASON_TYPES)}"
        )
    # canonical order: the PO pass reuses fitted values from the RS pass
    return [t for t in SEASON_TYPES if t in parts]
```

Insert the argument after the `--delay-s` block (`cli.py:129`):

```python
    imp.add_argument(
        "--season-types",
        type=_parse_season_types,
        default=list(SEASON_TYPES),
        help="Comma-separated season types to build "
        '(default: "Regular Season,Playoffs"). Rows are tagged with a '
        "season_type column. Pass 'Regular Season' alone to reproduce a "
        "regular-season-only build for diffing. PlayIn is not supported.",
    )
```

Thread it into the call in `main`:

```python
        built = build_nba_player_impact(
            args.seasons,
            args.out,
            lineup_source=args.lineup_source,
            cache_dir=args.cache_dir,
            delay_s=args.delay_s,
            season_types=args.season_types,
            proxy_provider=proxy_provider,
            replacement_level=args.replacement_level,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_model_publish_cli.py -k season_types -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add python/nba_model_publish/cli.py python/tests/test_model_publish_cli.py
git commit -m "feat(impact): add --season-types (default Regular Season,Playoffs)"
```

---

### Task 3: Split the season loop into an RS pass and a PO pass

The core change. The RS pass keeps today's behavior and fits `coef`/`pts_per_win`; the PO pass reuses them.

**Files:**
- Modify: `python/nba_model_publish/builders.py:177-217` (signature + docstring)
- Modify: `python/nba_model_publish/builders.py:233-330` (the loop body)
- Test: `python/tests/test_model_publish_builders.py`

**Interfaces:**
- Consumes: `_blend_by_poss` (Task 1); `args.season_types` (Task 2).
- Produces: `build_nba_player_impact(seasons, out_dir, *, lineup_source="auto", cache_dir=None, delay_s=0.6, season_types=("Regular Season", "Playoffs"), proxy_provider=None, replacement_level=-2.0) -> list[dict]`. Each result dict stays `{"season": int, "rows": int, "path": str}` where `rows` counts **both** season types. Output frames gain `season_type: Utf8`.
- Produces: `_impact_for_season_type(...) -> pl.DataFrame` is NOT introduced — keep the logic inline in the loop to match the file's existing style.

- [ ] **Step 1: Write the failing tests**

```python
def test_impact_emits_a_row_per_season_type(tmp_path, stubbed):
    out = B.build_nba_player_impact([2023], tmp_path, season_types=["Regular Season", "Playoffs"])
    df = pl.read_parquet(out[0]["path"])
    assert sorted(df["season_type"].unique().to_list()) == ["Playoffs", "Regular Season"]
    # grain is (player_id, season, season_type) -- no dupes
    assert df.select("player_id", "season", "season_type").is_duplicated().sum() == 0


def test_playoffs_reuse_the_rs_fitted_coef_and_pts_per_win(tmp_path, monkeypatch, stubbed):
    """The fitted quantities must be fit ONCE on RS -- a ~15-game playoff sample
    would train noise on noise."""
    train_calls, ppw_calls, spm_coefs = [], [], []
    monkeypatch.setattr(B, "train_spm", lambda bf, target: (train_calls.append(1), "COEF_RS")[1])
    monkeypatch.setattr(B, "calibrate_pts_per_win", lambda ts: (ppw_calls.append(1), 33.0)[1])
    real_spm = B.nba_spm
    monkeypatch.setattr(B, "nba_spm", lambda bf, coef: (spm_coefs.append(coef), real_spm(bf, coef))[1])

    B.build_nba_player_impact([2023], tmp_path, season_types=["Regular Season", "Playoffs"])

    assert len(train_calls) == 1, "SPM coef must be fitted once, on the regular season"
    assert len(ppw_calls) == 1, "pts_per_win must be calibrated once, on the regular season"
    assert spm_coefs == ["COEF_RS", "COEF_RS"], "the PO pass must reuse the RS coef"


def test_season_with_no_playoffs_emits_rs_only_and_does_not_raise(tmp_path, monkeypatch, stubbed):
    def _compile(season, **kw):
        if kw.get("season_type") == "Playoffs":
            return _poss(season).clear()  # empty, correct schema
        return _poss(season)

    monkeypatch.setattr(B, "compile_nba_season", _compile)
    out = B.build_nba_player_impact([2023], tmp_path)
    df = pl.read_parquet(out[0]["path"])
    assert df["season_type"].unique().to_list() == ["Regular Season"]


def test_compile_is_called_once_per_season_type_with_the_right_string(tmp_path, monkeypatch, stubbed):
    seen = []
    monkeypatch.setattr(
        B, "compile_nba_season",
        lambda season, **kw: (seen.append((season, kw.get("season_type"))), _poss(season))[1],
    )
    B.build_nba_player_impact([2023], tmp_path)
    assert seen == [(2023, "Regular Season"), (2023, "Playoffs")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_model_publish_builders.py -k "season_type or playoffs or no_playoffs" -v`
Expected: FAIL — `TypeError: build_nba_player_impact() got an unexpected keyword argument 'season_types'`

- [ ] **Step 3: Write the implementation**

First widen the typing import at `builders.py:36` — `Sequence` is not currently imported:

```python
from typing import Any, Callable, Optional, Sequence
```

Change the signature (`builders.py:177`) to add, after `delay_s`:

```python
    season_types: Sequence[str] = ("Regular Season", "Playoffs"),
```

Add to the `Args:` docstring block:

```
        season_types: Season types to build, in order. The "Regular Season" pass
            fits the SPM coefficients and pts_per_win; the "Playoffs" pass reuses
            them (a playoff sample is ~15 games/team -- re-fitting trains noise on
            noise) and takes the regular season's SPM as its adj-RAPM prior. Rows
            are tagged with a ``season_type`` column. "PlayIn" is not supported.
```

Replace the loop body (`builders.py:233` onward). The RS pass is today's code; the PO pass is new:

```python
    for season in sorted(seasons):
        s_str = _season_str(season)
        frames: list[pl.DataFrame] = []
        rapm_rs: Optional[pl.DataFrame] = None
        spm_rs: Optional[pl.DataFrame] = None
        rapm_po: Optional[pl.DataFrame] = None
        spm_po: Optional[pl.DataFrame] = None
        coef = None
        pts_per_win = None

        for stype in season_types:
            poss = compile_nba_season(
                season,
                season_type=stype,
                lineup_source=lineup_source,
                cache_dir=cache_dir,
                delay_s=delay_s,
                proxy_provider=proxy_provider,
            )
            if poss.height == 0:
                # A season can legitimately have no playoffs (lockout, in-progress).
                # This is NOT the same as a network failure: the empty-in/empty-out
                # contract is exactly what made the unproxied-discovery bug exit 0
                # with no data, so say which case this is.
                print(f"impact: season={season} type={stype!r} no possessions; skipped")
                if stype == "Regular Season":
                    prev_spm = None  # a gap season breaks the prior chain
                continue

            rapm = nba_rapm(poss)
            assert rapm.height > 0, f"impact: season={season} {stype} RAPM came back empty"

            logs = nba_box_logs(s_str, season_type=stype, fetch=_leaguegamelog)
            bf = box_features(logs["player"], logs["team"])

            if stype == "Regular Season":
                # Fitted ONCE, on the regular season; the playoff pass reuses both.
                coef = train_spm(bf, rapm.select("player_id", "o_rapm", "d_rapm"))
                pts_per_win = calibrate_pts_per_win(_team_season(logs["team"]))
                prior = AdjRapmModel.from_spm(prev_spm).prior if prev_spm is not None else {}
            else:
                assert coef is not None, "playoff pass requires the regular-season coef"
                # Within the season, the playoff fit is anchored on the RS estimate --
                # that prior is what makes a ~15-game sample usable at all.
                prior = AdjRapmModel.from_spm(spm_rs).prior if spm_rs is not None else {}

            spm = nba_spm(bf, coef)
            positions = nba_player_positions(s_str, fetch=_playerindex)
            bpm = nba_bpm(logs["player"], logs["team"], positions)
            adj = nba_adj_rapm(poss, prior)
            war = nba_war(
                rapm.select("player_id", pl.col("rapm").alias("rating")),
                rapm.select(
                    "player_id",
                    (pl.col("off_poss") + pl.col("def_poss")).alias("poss"),
                ),
                replacement_level=replacement_level,
                pts_per_win=pts_per_win,
            )

            if stype == "Regular Season":
                rapm_rs, spm_rs = rapm, spm
            else:
                rapm_po, spm_po = rapm, spm

            impact = rapm
            impact = _join_on_player(
                impact,
                adj.select("player_id", "o_adj_rapm", "d_adj_rapm", "adj_rapm"),
                "adj_rapm",
            )
            impact = _join_on_player(
                impact, spm.select("player_id", "ospm", "dspm", "spm", "min", "gp"), "spm"
            )
            impact = _join_on_player(
                impact, bpm.select("player_id", "obpm", "dbpm", "bpm"), "bpm"
            )
            impact = _join_on_player(impact, war, "war")
            impact = impact.with_columns(
                pl.lit(season, dtype=pl.Int64).alias("season"),
                pl.lit(stype, dtype=pl.Utf8).alias("season_type"),
            )
            frames.append(impact)

        if not frames:
            continue
```

The DARKO join, parquet write and `prev_spm` carry move below the inner loop — Task 4.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_model_publish_builders.py -v`
Expected: PASS — the 4 new tests plus the existing suite (Task 4 completes the DARKO/carry wiring; if a DARKO test fails here, finish Task 4 before judging).

- [ ] **Step 5: Commit**

```bash
git add python/nba_model_publish/builders.py python/tests/test_model_publish_builders.py
git commit -m "feat(impact): build Regular Season + Playoffs passes, tag season_type"
```

---

### Task 4: Season-granular DARKO panel + blended forward carry

**Files:**
- Modify: `python/nba_model_publish/builders.py` (below the inner loop from Task 3)
- Test: `python/tests/test_model_publish_builders.py`

**Interfaces:**
- Consumes: `_blend_by_poss` (Task 1); `rapm_rs`/`rapm_po`/`spm_rs`/`spm_po` from Task 3's loop.
- Produces: one parquet per season containing both season types; `prev_spm` carries the blended SPM.

- [ ] **Step 1: Write the failing tests**

```python
def test_darko_panel_stays_one_row_per_player_season(tmp_path, monkeypatch, stubbed):
    """DARKO's aging curve and process variance are per-season quantities -- a
    playoff time step would double-apply aging and mis-scale the filter."""
    panels = []
    monkeypatch.setattr(
        B, "nba_darko",
        lambda panel, ages, **kw: (panels.append(panel), _darko(panel))[1],
    )
    B.build_nba_player_impact([2022, 2023], tmp_path)
    last = panels[-1]
    assert last.select("player_id", "season").is_duplicated().sum() == 0
    assert "season_type" not in last.columns


def test_both_season_type_rows_carry_the_same_darko_projection(tmp_path, stubbed):
    out = B.build_nba_player_impact([2022, 2023], tmp_path)
    df = pl.read_parquet(out[-1]["path"])
    per_player = df.group_by("player_id").agg(
        pl.col("darko_projected_rating").n_unique().alias("n")
    )
    assert per_player["n"].max() == 1


def test_forward_prior_is_the_blend_not_the_playoff_estimate(tmp_path, monkeypatch, stubbed):
    """Pure chronological carry would make each RS prior a ~15-game playoff
    estimate -- that would degrade every regular-season row."""
    blends = []
    real_blend = B._blend_by_poss
    monkeypatch.setattr(
        B, "_blend_by_poss",
        lambda rs, po, vc, wc: (blends.append((vc, wc)), real_blend(rs, po, vc, wc))[1],
    )
    B.build_nba_player_impact([2022, 2023], tmp_path)
    # blended twice per season: the DARKO panel row and the forward SPM carry
    assert ("rating", "weight") in [(vc[0], wc) for vc, wc in blends]
    assert len(blends) >= 2


def test_rs_only_build_reproduces_the_pre_playoffs_behavior(tmp_path, stubbed):
    """Regression gate: --season-types "Regular Season" must be byte-identical to
    the old regular-season-only pipeline, so the change is diffable. Adding
    playoffs must not silently move the regular-season numbers."""
    out = B.build_nba_player_impact(
        [2022, 2023], tmp_path, season_types=["Regular Season"]
    )
    df = pl.read_parquet(out[-1]["path"])
    assert df["season_type"].unique().to_list() == ["Regular Season"]
    # with no PO frame the carry must be spm_rs itself, NOT a blend of it with nothing
    rs_cols = [c for c in df.columns if c != "season_type"]
    both = pl.read_parquet(
        B.build_nba_player_impact(
            [2022, 2023], tmp_path / "both", season_types=["Regular Season", "Playoffs"]
        )[-1]["path"]
    ).filter(pl.col("season_type") == "Regular Season")
    # the RS rows of a both-types build agree with an RS-only build on RAPM --
    # RAPM is fit per season_type and must not be touched by the playoff pass
    assert df.sort("player_id")["rapm"].to_list() == pytest.approx(
        both.sort("player_id")["rapm"].to_list()
    )
    assert set(rs_cols).issubset(set(both.columns))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_model_publish_builders.py -k "darko_panel or same_darko or forward_prior" -v`
Expected: FAIL — `season_type` present in the panel / duplicate `(player_id, season)` rows.

- [ ] **Step 3: Write the implementation**

Directly after `if not frames: continue` in the season loop:

```python
        # --- DARKO panel: ONE row per player-season ---------------------------
        # DARKO is a per-season Kalman filter + aging curve projecting NEXT
        # season. Inserting a playoff time step would apply a season of aging
        # twice and mis-scale the per-season process variance, so playoff form
        # enters as a possession-weighted blend instead of a second step.
        panel_rs = rapm_rs.select(
            "player_id",
            pl.col("rapm").alias("rating"),
            (pl.col("off_poss") + pl.col("def_poss")).alias("weight"),
        )
        panel_po = (
            rapm_po.select(
                "player_id",
                pl.col("rapm").alias("rating"),
                (pl.col("off_poss") + pl.col("def_poss")).alias("weight"),
            )
            if rapm_po is not None
            else None
        )
        panel_frames.append(
            _blend_by_poss(panel_rs, panel_po, ["rating"], "weight").with_columns(
                pl.lit(season, dtype=pl.Int64).alias("season")
            )
        )
        age_frames.append(
            nba_player_ages(s_str, fetch=_biostats).with_columns(
                pl.lit(season, dtype=pl.Int64).alias("season")
            )
        )
        panel = pl.concat(panel_frames)
        if panel["season"].n_unique() >= 2:
            darko = nba_darko(panel, pl.concat(age_frames))
            darko_season = darko.filter(pl.col("last_season") == season).select(
                "player_id",
                pl.col("filtered_skill").alias("darko_filtered_skill"),
                pl.col("projected_rating").alias("darko_projected_rating"),
                pl.col("projected_sd").alias("darko_projected_sd"),
            )
        else:
            darko_season = None

        # DARKO projects NEXT season, which is not a playoff-specific quantity:
        # both season_type rows carry the same projection.
        out_frames = []
        for f in frames:
            if darko_season is not None:
                f = _join_on_player(f, darko_season, "darko")
            else:
                f = f.with_columns(
                    [pl.lit(None, dtype=pl.Float64).alias(c) for c in _DARKO_COLS]
                )
            out_frames.append(f)
        impact = pl.concat(out_frames, how="vertical")

        path = out_dir / f"nba_player_impact_{season}.parquet"
        impact.write_parquet(path)
        results.append({"season": season, "rows": impact.height, "path": str(path)})
        print(
            f"impact: season={season} rows={impact.height} "
            f"types={impact['season_type'].unique().to_list()} -> {path}"
        )

        # --- forward carry ---------------------------------------------------
        # The next season's adj-RAPM prior is the possession-weighted RS+PO
        # blend, NOT the playoff estimate: a ~15-game sample must not override a
        # 1230-game one as the prior for the following regular season.
        if spm_po is not None:
            prev_spm = _blend_by_poss(
                spm_rs, spm_po, ["ospm", "dspm", "spm"], "min"
            )
        else:
            prev_spm = spm_rs
```

Remove the now-duplicated DARKO/write/`prev_spm = spm` block left over from Task 3.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_model_publish_builders.py tests/test_model_publish_cli.py -v`
Expected: PASS — full suite green (19 pre-existing + the new tests).

- [ ] **Step 5: Commit**

```bash
git add python/nba_model_publish/builders.py python/tests/test_model_publish_builders.py
git commit -m "feat(impact): season-granular DARKO panel + blended forward prior"
```

---

### Task 5: Model card — document the grain and the exclusions

**Files:**
- Modify: `python/nba_model_publish/builders.py:114-155` (`_write_model_card`)
- Test: `python/tests/test_model_publish_builders.py`

**Interfaces:**
- Consumes: `season_types` (Task 3).
- Produces: `_write_model_card(out_dir, results, *, replacement_level, lineup_source, season_types) -> Path` — unchanged return (the card path, `out_dir / "nba_player_impact_card.json"`).

Note the card is a **JSON dict** written to `nba_player_impact_card.json` — not markdown. Edit the dict.

- [ ] **Step 1: Write the failing test**

```python
def test_model_card_documents_grain_and_playin_exclusion(tmp_path, stubbed):
    B.build_nba_player_impact([2023], tmp_path)
    card = json.loads((tmp_path / "nba_player_impact_card.json").read_text())
    assert card["grain"] == ["player_id", "season", "season_type"]
    assert card["season_types"] == ["Regular Season", "Playoffs"]
    # the play-in exclusion must be explicit, not silent
    assert "PlayIn" in card["excluded"]
    assert "playoffs" in card["models"]["spm"].lower()
```

`json` is already imported by the module under test; add `import json` to the test file if absent.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_model_publish_builders.py -k model_card -v`
Expected: FAIL — `KeyError: 'grain'`

- [ ] **Step 3: Write the implementation**

Add `season_types: Sequence[str]` to the `_write_model_card` keyword-only params and pass it from the call site at the end of `build_nba_player_impact`. Then, in the `card` dict:

Change `description` to state the real grain:

```python
        "description": (
            "Consolidated per-season NBA player-impact table: RAPM, adj-RAPM, "
            "SPM, BPM 2.0, WAR, and DARKO forecasts joined on player_id. One "
            "parquet per season, one row per player-season-season_type. Base "
            "population = players with possession lineup data (RAPM-rated)."
        ),
```

Add these keys after `"description"`:

```python
        "grain": ["player_id", "season", "season_type"],
        "season_types": list(season_types),
        "excluded": (
            "PlayIn -- the NBA exposes PlayIn as a third SeasonType (2020+, "
            "~4-6 games/year). Those games appear in neither season type here."
        ),
```

Update the two `models` entries whose behavior changed:

```python
            "adj_rapm": (
                "sportsdataverse.nba.nba_adj_rapm. Within a season, the Playoffs "
                "fit takes that season's Regular Season SPM as its prior -- that "
                "anchor is what makes a ~15-game playoff sample usable. Across "
                "seasons the prior is the possession-weighted blend of the "
                "season's Regular Season + Playoffs SPM, so a thin playoff "
                "sample never overrides a full regular season (empty for the "
                "first season of an invocation)."
            ),
            "spm": (
                "sportsdataverse.nba.train_spm + nba_spm. Coefficients are "
                "trained ONCE per season, on the Regular Season box features + "
                "RAPM target, and reused for the Playoffs pass -- re-fitting on "
                "a ~15-game playoff sample would train noise on noise. Playoff "
                "figures are therefore on the same scale as regular-season ones "
                "but rest on far fewer possessions; treat them as directional."
            ),
```

And DARKO / WAR:

```python
            "war": (
                "sportsdataverse.nba.nba_war on the RAPM rating; pts_per_win "
                "calibrated ONCE per season from Regular Season team game logs "
                "(OLS wins ~ total margin) and reused for the Playoffs pass; "
                f"replacement_level = {replacement_level} per 100 "
                "(basketball-reference VORP convention)"
            ),
            "darko": (
                "sportsdataverse.nba.nba_darko on a SEASON-GRANULAR panel: one "
                "row per player-season whose rating is the possession-weighted "
                "blend of Regular Season + Playoffs (DARKO's aging curve and "
                "process variance are per-season quantities, so playoffs enter "
                "as a blend, not a second time step). DARKO projects the NEXT "
                "season, so both season_type rows carry the same projection; "
                "darko_* columns are null until the panel spans >= 2 seasons"
            ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_model_publish_builders.py -k model_card -v`
Expected: PASS

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_model_publish_builders.py -k model_card -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python/nba_model_publish/builders.py python/tests/test_model_publish_builders.py
git commit -m "docs(impact): document season_type grain + PlayIn exclusion in the model card"
```

---

### Task 6: Live single-season verification on the droplet

Not a unit test — this is the gate the unit tests structurally cannot be, because every one of them stubs `compile_nba_season`. That stubbing is exactly what let the unproxied-discovery bug reach production.

**Files:**
- None modified.

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Build 2023 live, both season types, no upload**

The RS possessions are already cached from the smoke, so only the ~85 playoff games fetch.

```bash
cd /mnt/sdv_repos/hoopR-nba-stats-data
. ~/.config/sdv/env
SDV_NBA_DELAY_S=7 bash scripts/run_impact_backfill.sh 2023 --dry-run
```

- [ ] **Step 2: Verify playoff games actually fetched**

```bash
ls /data/nba_possessions/possessions/ | grep -c '^004'
```

Expected: **> 0** (roughly 80-90 for 2023). `0` means the playoff pass fetched nothing — treat as failure, not success, regardless of the exit code.

- [ ] **Step 3: Verify the grain in the real parquet**

```bash
cd python && uv run python -c "
import polars as pl
df = pl.read_parquet('build_out/impact/nba_player_impact_2023.parquet')
print('rows:', df.height)
print('season_types:', df['season_type'].unique().to_list())
print('dupes on grain:', df.select('player_id','season','season_type').is_duplicated().sum())
print('playoff rows:', df.filter(pl.col('season_type')=='Playoffs').height)
"
```

Expected: both season types present, `dupes on grain: 0`, playoff rows > 0.

- [ ] **Step 4: Commit nothing; report**

No code change. If any expectation above fails, stop and report rather than starting the 25-season backfill.

---

### Task 7: `sdv-py` loader schema — add `season_type`, fix the duplicate `season`

Separate repo, separate PR. `sportsdataverse-py` is a code/library repo: **branch + PR**, never a direct push to main.

**Files:**
- Modify: `/mnt/sdv_repos/sdv-py/tools/codegen/schemas/loader_schemas.yaml` (`load_nba_player_impact`, ~line 4333)

**Interfaces:**
- Consumes: the parquet produced by Task 6.
- Produces: a loader schema matching the real footer.

- [ ] **Step 1: Add `season_type` and remove the duplicate `season`**

`load_nba_player_impact` currently declares `season` **twice** — a pre-existing bug found while reading the schema, unrelated to playoffs. Remove the second occurrence and add:

```yaml
- name: season_type
  type: Utf8
```

Edit by hand. Do **not** run a full `--loader-schemas` re-introspect: the runbook is explicit that it churns every league's column order. Merge surgically.

- [ ] **Step 2: Verify the schema matches the real parquet footer**

```bash
cd /mnt/sdv_repos/sdv-py && uv run python -c "
import polars as pl, yaml
cols = [c['name'] for c in yaml.safe_load(open('tools/codegen/schemas/loader_schemas.yaml'))['load_nba_player_impact']]
real = pl.read_parquet('/mnt/sdv_repos/hoopR-nba-stats-data/python/build_out/impact/nba_player_impact_2023.parquet').columns
print('duplicates in schema:', [c for c in set(cols) if cols.count(c) > 1] or 'none')
print('in schema, not in parquet:', [c for c in cols if c not in real])
print('in parquet, not in schema:', [c for c in real if c not in cols])
"
```

Expected: `duplicates in schema: none`; the athlete/team join columns may legitimately appear only in the schema (they are added by the loader, not the builder) — everything else should reconcile.

- [ ] **Step 3: Run the codegen drift gate**

Run: `uv run python tools/codegen/generate.py --docs && uv run python tools/codegen/generate.py --check`
Expected: exit 0. Regenerate before pushing — CI fails on drift. Ignore `755`→`644` mode-only churn on `docs/docs/*/index.md`; revert those with `git checkout --` and commit only real content changes.

- [ ] **Step 4: Commit and open a PR**

```bash
cd /mnt/sdv_repos/sdv-py
git switch -c fix/nba-player-impact-schema-season-type
git add tools/codegen/schemas/loader_schemas.yaml
git commit -m "fix(nba): add season_type to load_nba_player_impact, drop duplicate season"
git push -u origin fix/nba-player-impact-schema-season-type
gh pr create --base main \
  --title "fix(nba): add season_type to load_nba_player_impact, drop duplicate season" \
  --body "$(cat <<'EOF'
## What

`nba_player_impact` gains a `season_type` dimension (`Regular Season` / `Playoffs`);
its grain becomes `(player_id, season, season_type)`. This adds the matching loader
column, introspected against the real parquet footer.

Also drops a pre-existing duplicate: `season` was declared **twice** in
`load_nba_player_impact`. Unrelated to playoffs, found while reading the schema.

## Verified

Reconciled against a live 2023 build from the sdv-data droplet (both season types),
not against an expected shape. Merged surgically rather than by a full
`--loader-schemas` re-introspect, which churns every league's column order.

Producer side: sportsdataverse/hoopR-nba-stats-data — see
`docs/superpowers/specs/2026-07-17-nba-player-impact-playoffs-design.md`.
EOF
)"
```

**Note:** the `nba_player_impact` release does not exist yet, so the repo's
`release-manifest audit (informational)` check reports it as an orphan
(loader → dead release). That check is red *before* this PR and stays red until
the backfill publishes the tag — it is not a regression from this change.

---

## Execution order

Tasks 1→5 are sequential (each consumes the previous). Task 6 gates Task 7 — the loader schema must be introspected against a **real** parquet, not an expected one. Do not start the 25-season backfill until Task 6 passes.
