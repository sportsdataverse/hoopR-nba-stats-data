"""BB-D38 columns and the BB-D39 current-impact build, on real NBA slices (tests/fixtures/prior_informed)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from nba_model_publish import prior_informed as P
from sportsdataverse.nba import nba_box_logs
from sportsdataverse.nba.nba_box_prior import BOX_PRIOR_FEATURES, apply_box_prior

FX = Path(__file__).parent / "fixtures" / "prior_informed"


@pytest.fixture(scope="module")
def models():
    return P.load_box_prior_models()


@pytest.fixture(scope="module")
def data():
    return load_data()


def load_data():
    logs = pl.read_parquet(FX / "leaguegamelog_2014_2015.parquet")
    frames = {}
    for (s, pt), f in logs.group_by("_season", "_pt"):
        f = f.drop("_season", "_pt")
        frames[(f"{s - 1}-{s % 100:02d}", pt)] = f.select(
            c for c in f.columns if f[c].null_count() < f.height
        )
    return {
        "poss": pl.read_parquet(FX / "possessions_2014_2015.parquet"),
        "logs": frames,
        "index": pl.read_parquet(FX / "playerindex_2015.parquet"),
        "bio": pl.read_parquet(FX / "biostats_2015.parquet"),
    }


def _fetches(data):
    def leaguegamelog(**kw):
        pt = str(kw.get("player_or_team_abbreviation") or "T").upper()
        empty = data["logs"][("2013-14", pt)].clear()  # 2012-13 is not in the fixture
        return data["logs"].get((kw["season"], pt), empty)

    # one season of bio stats in the fixture (2014-15), used for 2013-14's window priors too
    return {
        "leaguegamelog": leaguegamelog,
        "playerindex": lambda **kw: data["index"],
        "biostats": lambda **kw: data["bio"],
    }


def test_committed_models_reproduce_the_d38_fit_priors(models):
    """The JSON export is the fit: applying it to the fit's own features gives the fit's priors."""
    fx = pl.read_parquet(FX / "d38_fit_features_priors.parquet")
    for (s,), f in fx.group_by("season"):
        got = apply_box_prior(f.select("player_id", *BOX_PRIOR_FEATURES), models[s])
        np.testing.assert_allclose(got["o_prior"], f["o_prior"], rtol=0, atol=1e-9)
        np.testing.assert_allclose(got["d_prior"], f["d_prior"], rtol=0, atol=1e-9)


def test_models_are_walk_forward(models):
    assert sorted(models) == list(range(1997, 2028))
    for s, m in models.items():
        assert s not in m.train_seasons
        if s > 2005:
            assert max(m.train_seasons) == s - 1, s  # every earlier season, nothing later
    assert models[2027].train_seasons == list(range(1997, 2027))


def test_box_prior_columns_on_a_real_season_slice(data, models):
    poss = data["poss"].filter(pl.col("season") == 2015)
    lg = nba_box_logs(
        "2014-15", season_type="Regular Season", fetch=_fetches(data)["leaguegamelog"]
    )
    bio = P.season_bio(
        P.nba_player_ages("2014-15", fetch=_fetches(data)["biostats"]), data["index"]
    )
    out = P.box_prior_columns(poss, lg["player"], lg["team"], bio, models[2015])
    on_court = poss.select(
        pl.concat_list([c for c in poss.columns if "_player_" in c]).explode().unique()
    )
    assert out.columns == ["player_id", *P.D38_COLUMNS]
    assert out["player_id"].n_unique() == out.height == on_court.height
    assert out.select(pl.all().null_count()).sum_horizontal().item() == 0
    np.testing.assert_allclose(out["box_prior"], out["o_box_prior"] + out["d_box_prior"])
    np.testing.assert_allclose(out["reml_rapm"], out["o_reml_rapm"] + out["d_reml_rapm"])
    # two weeks of games are mostly prior (observed r 0.88), but the possessions still move it
    assert out.select(pl.corr("reml_rapm", "box_prior")).item() > 0.8
    assert (out["reml_rapm"] - out["box_prior"]).abs().max() > 0.1


def _build(data, models, tmp_path, poss=None):
    """The filter from 2013-14 (its April games) into 2014-15 (games before 2014-11-08)."""
    poss = data["poss"] if poss is None else poss
    return P.build_nba_current_impact(
        [2015],
        tmp_path,
        compile_season=lambda s: poss.filter(pl.col("season") == s),
        models=models,
        start=2014,
        **_fetches(data),
    )


def test_current_impact_build(data, models, tmp_path):
    (res,) = _build(data, models, tmp_path)
    out = pl.read_parquet(res["path"])
    assert res["rows"] == out.height > 0
    assert out["as_of"].unique().sort().to_list() == [dt.date(2014, 10, 28), dt.date(2014, 11, 4)]
    assert out["season"].unique().to_list() == [
        2015
    ]  # opening night too (its last games are 2014's)
    assert out.select(pl.struct("player_id", "as_of").is_unique().all()).item()
    assert (out["last_game_date"] < out["as_of"]).all()
    assert (out["as_of"] - out["last_game_date"] <= dt.timedelta(days=P.ACTIVE_DAYS)).all()
    night = out.filter(pl.col("as_of") == dt.date(2014, 10, 28))
    assert night.height > 300 and (night["off_poss"] == 0).all()  # no 2014-15 game yet ...
    assert (
        night["o_prior"].abs().min() > 0
    )  # ... but last season's box lines give every player a prior
    np.testing.assert_allclose(
        out["current_impact"], out["o_current_impact"] + out["d_current_impact"]
    )
    for ext in ("csv", "rds"):
        assert Path(res["path"]).with_suffix(f".{ext}").exists()


def _at(res, day):
    return pl.read_parquet(res["path"]).filter(pl.col("as_of") == day).sort("player_id")


def test_current_impact_reads_only_games_before_the_date(data, models, tmp_path):
    """Rewriting the possessions on or after 2014-11-04 leaves that date's ratings unchanged;
    rewriting the week before it moves them (so the comparison can fail)."""
    cut = dt.date(2014, 11, 4)
    base = _at(_build(data, models, tmp_path / "a")[0], cut)

    def rewritten(cond):
        return data["poss"].with_columns(
            pl.when(cond).then(3).otherwise(pl.col("points")).alias("points")
        )

    after = _at(_build(data, models, tmp_path / "b", rewritten(pl.col("game_date") >= cut))[0], cut)
    week = pl.col("game_date").is_between(dt.date(2014, 10, 28), cut, closed="left")
    before = _at(_build(data, models, tmp_path / "c", rewritten(week))[0], cut)
    assert base["player_id"].equals(after["player_id"]) and base.height > 300
    # reruns differ by ~1e-16 (summation order), so compare to 1e-12
    np.testing.assert_allclose(after["current_impact"], base["current_impact"], rtol=0, atol=1e-12)
    assert (before["current_impact"] - base["current_impact"]).abs().max() > 0.1


def test_current_impact_needs_a_model_for_every_filter_season(data, models, tmp_path):
    with pytest.raises(ValueError, match="no box prior model"):
        _build(data, {k: v for k, v in models.items() if k != 2015}, tmp_path)


def test_append_d38_keeps_every_published_column(tmp_path):
    """The backfill path: published bytes untouched, D38 columns appended from the rebuild."""
    pub = pl.DataFrame(
        {
            "player_id": [2, 1, 1],
            "season_type": ["Regular Season", "Regular Season", "Playoffs"],
            "rapm": [0.1, 0.2, 0.3],
        }
    )
    built = pl.DataFrame(
        {"player_id": [1, 1, 2], "season_type": ["Playoffs", "Regular Season", "Regular Season"]}
        | {c: [None, 1.0, 2.0] for c in P.D38_COLUMNS}
    )
    out = P.append_d38(pub, built)
    assert out.select(pub.columns).equals(pub)
    assert out.columns == [*pub.columns, *P.D38_COLUMNS]
    assert out["reml_rapm"].to_list() == [2.0, 1.0, None]
    with pytest.raises(ValueError, match="players differ"):
        P.append_d38(pub, built.head(2))
