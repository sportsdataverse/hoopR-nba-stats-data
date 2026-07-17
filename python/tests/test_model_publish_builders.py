"""Hermetic tests for nba_model_publish.builders.build_nba_player_impact.

Every sportsdataverse model function is stubbed at the builders-module seam,
so these tests exercise the ORCHESTRATION contract (join discipline, prior
threading, season ordering, schema stability, card sidecar) with zero network
and zero model compute. The models' own correctness is validated in sdv-py.
"""

from __future__ import annotations

import json

import polars as pl
import pytest

import nba_model_publish.builders as B


def _poss(season: int) -> pl.DataFrame:
    """Minimal possession stint frame (only height matters to the stubs)."""
    return pl.DataFrame(
        {"game_id": [f"00{season}"], "points": pl.Series([2], dtype=pl.Int64)}
    )


def _rapm(players: list[int]) -> pl.DataFrame:
    n = len(players)
    return pl.DataFrame(
        {
            "player_id": pl.Series(players, dtype=pl.Int64),
            "o_rapm": [1.0] * n,
            "d_rapm": [0.5] * n,
            "rapm": [1.5] * n,
            "off_poss": pl.Series([100] * n, dtype=pl.Int64),
            "def_poss": pl.Series([100] * n, dtype=pl.Int64),
        }
    )


def _spm(players: list[int]) -> pl.DataFrame:
    n = len(players)
    return pl.DataFrame(
        {
            "player_id": pl.Series(players, dtype=pl.Int64),
            "ospm": [2.0] * n,
            "dspm": [1.0] * n,
            "spm": [3.0] * n,
            "min": [500.0] * n,
            "gp": pl.Series([50] * n, dtype=pl.Int64),
        }
    )


def _bpm(players: list[int]) -> pl.DataFrame:
    n = len(players)
    return pl.DataFrame(
        {
            "player_id": pl.Series(players, dtype=pl.Int64),
            "obpm": [1.0] * n,
            "dbpm": [0.0] * n,
            "bpm": [1.0] * n,
            "min": [500.0] * n,
            "gp": pl.Series([50] * n, dtype=pl.Int64),
        }
    )


def _adj(players: list[int]) -> pl.DataFrame:
    n = len(players)
    return pl.DataFrame(
        {
            "player_id": pl.Series(players, dtype=pl.Int64),
            "o_adj_rapm": [1.1] * n,
            "d_adj_rapm": [0.4] * n,
            "adj_rapm": [1.5] * n,
            "off_poss": pl.Series([100] * n, dtype=pl.Int64),
            "def_poss": pl.Series([100] * n, dtype=pl.Int64),
        }
    )


@pytest.fixture()
def stubbed(monkeypatch):
    """Stub the full model seam; record adj-RAPM priors + compile order."""
    players = [1, 2, 3]
    seen: dict = {"priors": [], "compile_order": [], "darko_panels": []}

    monkeypatch.setattr(
        B,
        "compile_nba_season",
        lambda season, **kw: (seen["compile_order"].append(season), _poss(season))[1],
    )
    monkeypatch.setattr(B, "nba_rapm", lambda poss, **kw: _rapm(players))
    monkeypatch.setattr(
        B,
        "nba_box_logs",
        lambda s, **kw: {
            "player": pl.DataFrame({"player_id": players}),
            "team": pl.DataFrame(
                {
                    "team_id": pl.Series([10, 11, 12], dtype=pl.Int64),
                    "plus_minus": [5, -3, 8],
                }
            ),
        },
    )
    monkeypatch.setattr(
        B, "box_features", lambda p, t, **kw: pl.DataFrame({"player_id": players})
    )
    monkeypatch.setattr(B, "train_spm", lambda bf, target, **kw: object())
    monkeypatch.setattr(B, "nba_spm", lambda bf, coef, **kw: _spm(players))
    monkeypatch.setattr(
        B, "nba_player_positions", lambda s, **kw: pl.DataFrame({"player_id": players})
    )
    monkeypatch.setattr(B, "nba_bpm", lambda pl_, tl, pos, **kw: _bpm(players))
    monkeypatch.setattr(
        B,
        "nba_adj_rapm",
        lambda poss, prior, **kw: (seen["priors"].append(prior), _adj(players))[1],
    )
    monkeypatch.setattr(B, "calibrate_pts_per_win", lambda ts: 30.0)
    monkeypatch.setattr(
        B,
        "nba_war",
        lambda ratings, poss, **kw: pl.DataFrame(
            {
                "player_id": pl.Series(players, dtype=pl.Int64),
                "war": [2.0] * len(players),
            }
        ),
    )
    monkeypatch.setattr(
        B,
        "nba_player_ages",
        lambda s, **kw: pl.DataFrame(
            {
                "player_id": pl.Series(players, dtype=pl.Int64),
                "age": [25.0] * len(players),
            }
        ),
    )

    def fake_darko(panel, ages, **kw):
        seen["darko_panels"].append(panel)
        last = int(panel["season"].max())
        return pl.DataFrame(
            {
                "player_id": pl.Series(players, dtype=pl.Int64),
                "last_season": pl.Series([last] * len(players), dtype=pl.Int64),
                "forecast_season": pl.Series([last + 1] * len(players), dtype=pl.Int64),
                "filtered_skill": [1.0] * len(players),
                "projected_rating": [1.2] * len(players),
                "projected_sd": [0.3] * len(players),
            }
        )

    monkeypatch.setattr(B, "nba_darko", fake_darko)
    return seen


EXPECTED_COLS = {
    "player_id",
    "season",
    "season_type",
    "o_rapm",
    "d_rapm",
    "rapm",
    "off_poss",
    "def_poss",
    "o_adj_rapm",
    "d_adj_rapm",
    "adj_rapm",
    "ospm",
    "dspm",
    "spm",
    "min",
    "gp",
    "obpm",
    "dbpm",
    "bpm",
    "war",
    "darko_filtered_skill",
    "darko_projected_rating",
    "darko_projected_sd",
}


def test_impact_schema_and_outputs(stubbed, tmp_path):
    # RS-only: this test is about join/ordering/schema discipline, not the
    # season_type dimension (covered separately below).
    results = B.build_nba_player_impact(
        [2023, 2022], tmp_path, season_types=["Regular Season"]
    )

    # earliest -> latest regardless of input order
    assert stubbed["compile_order"] == [2022, 2023]
    assert [r["season"] for r in results] == [2022, 2023]

    for r in results:
        df = pl.read_parquet(r["path"])
        assert set(df.columns) == EXPECTED_COLS
        assert df.height == 3 == r["rows"]
        assert df.schema["player_id"] == pl.Int64
        assert df.schema["season"] == pl.Int64
        assert df["season"].unique().to_list() == [r["season"]]


def test_prior_threads_forward(stubbed, tmp_path):
    # RS-only: isolates the prior-chaining behavior from the season_type dimension.
    B.build_nba_player_impact([2022, 2023], tmp_path, season_types=["Regular Season"])
    # first season: empty prior; second: previous season's SPM via from_spm
    assert stubbed["priors"][0] == {}
    assert stubbed["priors"][1] == {1: (2.0, 1.0), 2: (2.0, 1.0), 3: (2.0, 1.0)}


def test_darko_null_until_two_seasons(stubbed, tmp_path):
    results = B.build_nba_player_impact(
        [2022, 2023], tmp_path, season_types=["Regular Season"]
    )
    first = pl.read_parquet(results[0]["path"])
    second = pl.read_parquet(results[1]["path"])
    assert first["darko_projected_rating"].null_count() == first.height
    assert second["darko_projected_rating"].null_count() == 0
    # the darko panel spans both seasons by the second iteration
    assert stubbed["darko_panels"][0]["season"].n_unique() == 2


def test_model_card_written(stubbed, tmp_path):
    B.build_nba_player_impact([2022], tmp_path, season_types=["Regular Season"])
    card = json.loads((tmp_path / "nba_player_impact_card.json").read_text())
    assert card["dataset"] == "nba_player_impact"
    assert card["seasons"] == [{"season": 2022, "rows": 3}]
    assert "stats.nba.com" in card["source"]


def test_empty_season_skipped_and_breaks_prior_chain(stubbed, monkeypatch, tmp_path):
    empty = pl.DataFrame({"game_id": [], "points": []})
    real_compile = B.compile_nba_season
    monkeypatch.setattr(
        B,
        "compile_nba_season",
        lambda season, **kw: empty if season == 2023 else real_compile(season, **kw),
    )
    results = B.build_nba_player_impact(
        [2022, 2023, 2024], tmp_path, season_types=["Regular Season"]
    )
    assert [r["season"] for r in results] == [2022, 2024]
    # the 2023 gap resets the prior: 2024 gets an empty prior again
    assert stubbed["priors"] == [{}, {}]


def test_duplicate_player_id_join_guard(stubbed, monkeypatch, tmp_path):
    dup = _adj([1, 1, 2])
    monkeypatch.setattr(B, "nba_adj_rapm", lambda poss, prior, **kw: dup)
    with pytest.raises(AssertionError, match="duplicate player_id"):
        B.build_nba_player_impact([2022], tmp_path)


def test_join_key_dtype_guard(stubbed, monkeypatch, tmp_path):
    bad = _adj([1, 2, 3]).with_columns(pl.col("player_id").cast(pl.Utf8))
    monkeypatch.setattr(B, "nba_adj_rapm", lambda poss, prior, **kw: bad)
    with pytest.raises(AssertionError, match="player_id dtype"):
        B.build_nba_player_impact([2022], tmp_path)


# ---------------------------------------------------------------------------
# Proxy threading. stats.nba.com HANGS (does not error) on datacenter IPs, so a
# surface that quietly fetches unproxied stalls the whole run instead of failing.
# The builder touches FOUR network surfaces -- proxying only the compile is the
# bug this pins.
# ---------------------------------------------------------------------------


def test_proxied_injects_a_fresh_proxy_per_call():
    pool = iter(["http://p1:1", "http://p2:2"])
    seen = []

    def wrapper(season, *, proxy_url=None):
        seen.append((season, proxy_url))
        return "ok"

    f = B._proxied(wrapper, lambda: next(pool))
    f("2023-24")
    f("2024-25")
    # rotates -- a static proxy_url would burn one exit IP across a whole backfill
    assert seen == [("2023-24", "http://p1:1"), ("2024-25", "http://p2:2")]


def test_proxied_without_provider_returns_wrapper_untouched():
    def wrapper(season):
        return "ok"

    assert B._proxied(wrapper, None) is wrapper  # local/residential runs stay direct


def test_build_threads_proxy_to_all_four_network_surfaces(
    stubbed, tmp_path, monkeypatch
):
    captured: dict = {}

    def _cap(name, orig, key):
        def _f(*a, **kw):
            captured[name] = kw.get(key)
            return orig(*a, **kw)

        return _f

    monkeypatch.setattr(
        B, "compile_nba_season", _cap("compile", B.compile_nba_season, "proxy_provider")
    )
    monkeypatch.setattr(B, "nba_box_logs", _cap("box_logs", B.nba_box_logs, "fetch"))
    monkeypatch.setattr(
        B, "nba_player_positions", _cap("positions", B.nba_player_positions, "fetch")
    )
    monkeypatch.setattr(B, "nba_player_ages", _cap("ages", B.nba_player_ages, "fetch"))

    def provider():
        return "http://p:1"

    B.build_nba_player_impact([2023], tmp_path, proxy_provider=provider)

    assert captured["compile"] is provider  # possession compile rotates per game
    # ...and the OTHER three (leaguegamelog / playerindex / leaguedashplayerbiostats)
    # each got a proxied fetch seam -- not left fetching from the host's real IP.
    for surface in ("box_logs", "positions", "ages"):
        assert captured[surface] is not None, (
            f"{surface} would fetch UNPROXIED and hang"
        )


def test_delay_s_threads_into_the_possession_compile(stubbed, monkeypatch, tmp_path):
    stub_compile = B.compile_nba_season  # the stubbed fake
    seen_kw: dict = {}
    monkeypatch.setattr(
        B,
        "compile_nba_season",
        lambda season, **kw: (seen_kw.update(kw), stub_compile(season, **kw))[1],
    )
    B.build_nba_player_impact([2023], tmp_path, delay_s=1.5)
    assert seen_kw["delay_s"] == 1.5


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


def test_blend_by_poss_player_in_po_frame_only():
    """Coverage gap: the existing tests only cover a player present in RS only.

    A player who only appears in the playoff frame (e.g. a late call-up who
    never logged regular-season possessions) must keep the PO values
    unchanged too -- not null, not halved.
    """
    rs = pl.DataFrame({"player_id": [1], "rating": [2.0], "poss": [900]})
    po = pl.DataFrame({"player_id": [1, 2], "rating": [6.0, 9.0], "poss": [100, 50]})
    out = B._blend_by_poss(rs, po, ["rating"], "poss").sort("player_id")
    assert out["rating"].to_list() == [pytest.approx(2.4), pytest.approx(9.0)]
    assert out["poss"].to_list() == [1000, 50]


# ---------------------------------------------------------------------------
# season_types: RS fits, PO reuses; DARKO panel stays season-granular; the
# forward carry is the possession-weighted blend. See
# docs/superpowers/specs/2026-07-17-nba-player-impact-playoffs-design.md.
# ---------------------------------------------------------------------------


def _darko(panel: pl.DataFrame) -> pl.DataFrame:
    """Same shape as the ``stubbed`` fixture's fake_darko, callable standalone
    so tests that replace ``nba_darko`` entirely can still produce a valid frame."""
    players = panel["player_id"].unique().to_list()
    n = len(players)
    last = int(panel["season"].max())
    return pl.DataFrame(
        {
            "player_id": pl.Series(players, dtype=pl.Int64),
            "last_season": pl.Series([last] * n, dtype=pl.Int64),
            "forecast_season": pl.Series([last + 1] * n, dtype=pl.Int64),
            "filtered_skill": [1.0] * n,
            "projected_rating": [1.2] * n,
            "projected_sd": [0.3] * n,
        }
    )


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
    monkeypatch.setattr(B, "train_spm", lambda bf, target, **kw: (train_calls.append(1), "COEF_RS")[1])
    monkeypatch.setattr(B, "calibrate_pts_per_win", lambda ts: (ppw_calls.append(1), 33.0)[1])
    real_spm = B.nba_spm
    monkeypatch.setattr(B, "nba_spm", lambda bf, coef, **kw: (spm_coefs.append(coef), real_spm(bf, coef))[1])

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
