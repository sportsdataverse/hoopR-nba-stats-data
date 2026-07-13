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
    results = B.build_nba_player_impact([2023, 2022], tmp_path)

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
    B.build_nba_player_impact([2022, 2023], tmp_path)
    # first season: empty prior; second: previous season's SPM via from_spm
    assert stubbed["priors"][0] == {}
    assert stubbed["priors"][1] == {1: (2.0, 1.0), 2: (2.0, 1.0), 3: (2.0, 1.0)}


def test_darko_null_until_two_seasons(stubbed, tmp_path):
    results = B.build_nba_player_impact([2022, 2023], tmp_path)
    first = pl.read_parquet(results[0]["path"])
    second = pl.read_parquet(results[1]["path"])
    assert first["darko_projected_rating"].null_count() == first.height
    assert second["darko_projected_rating"].null_count() == 0
    # the darko panel spans both seasons by the second iteration
    assert stubbed["darko_panels"][0]["season"].n_unique() == 2


def test_model_card_written(stubbed, tmp_path):
    B.build_nba_player_impact([2022], tmp_path)
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
    results = B.build_nba_player_impact([2022, 2023, 2024], tmp_path)
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
