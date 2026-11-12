"""Prior-informed NBA ratings: the BB-D38 season columns and the BB-D39 weekly current rating.

* **BB-D38** (:func:`box_prior_columns`, joined onto the Regular Season rows of ``nba_player_impact``):
  sportsdataverse's box prior v2 for the season (``o_box_prior`` / ``d_box_prior`` / ``box_prior``) and the
  season rating shrunk toward it at the league's fixed adjusted-RAPM penalty
  (``nba_reml_rapm(penalty="fixed")``: ``o_reml_rapm`` / ``d_reml_rapm`` / ``reml_rapm``). Per 100
  possessions, ``d`` positive = good defense.
* **BB-D39** (:func:`build_nba_current_impact`, release ``nba_current_impact``): ``nba_current_impact`` at
  opening night and every 7 days after it, one row per player per as-of date, from the games before the
  date only.

The box prior models are fitted by sportsdataverse-py ``tools/fit_box_prior_v2.py`` (walk-forward: the
model for season ``s`` learned from earlier seasons only, leave-one-season-out through 2005) and committed
here as :data:`MODELS_PATH` by ``scripts/export_box_prior_models.py``. A season with no model gets null
BB-D38 columns.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Callable, Optional

import polars as pl
from nba_data_build.reshape.io import RDS_CLASS
from sportsdataverse._rds import write_rds
from sportsdataverse.nba import nba_box_logs, nba_player_ages
from sportsdataverse.nba.nba_box_prior import BoxPriorModel, apply_box_prior, box_prior_features
from sportsdataverse.nba.nba_current_impact import current_impact_prior, nba_current_impact
from sportsdataverse.nba.nba_player_positions import _position_to_num
from sportsdataverse.nba.nba_reml_rapm import nba_reml_rapm

MODELS_PATH = Path(__file__).resolve().parents[2] / "models" / "box_prior_v2.json"

#: BB-D38 columns added to ``nba_player_impact`` (Regular Season rows; null on Playoffs rows).
D38_COLUMNS = ["o_box_prior", "d_box_prior", "box_prior", "o_reml_rapm", "d_reml_rapm", "reml_rapm"]

#: The current rating's first season: the box prior is walk-forward from 2006 (earlier models learned
#: from later seasons), matching sportsdataverse-py ``tools/fit_current_impact.py``. 2006 is warm-up only.
CURRENT_IMPACT_START = 2006
STEP_DAYS = 7
#: A player is listed on a date while his last game is at most this many days before it (drops retirees).
ACTIVE_DAYS = 365

_OFF = [f"off_player_{i}" for i in range(1, 6)]
_DEF = [f"def_player_{i}" for i in range(1, 6)]

Fetch = Callable[..., pl.DataFrame]


def model_record(m: BoxPriorModel) -> dict:
    """A :class:`BoxPriorModel` as a JSON-able dict (the :data:`MODELS_PATH` record)."""
    return {
        "season": int(m.season),
        "train_seasons": [int(s) for s in m.train_seasons],
        "feature_names": list(m.feature_names),
        "o_coef": m.o_coef.tolist(),
        "o_intercept": m.o_intercept.tolist(),
        "d_coef": m.d_coef.tolist(),
        "d_intercept": m.d_intercept.tolist(),
    }


def load_box_prior_models(path: Path = MODELS_PATH) -> dict[int, BoxPriorModel]:
    """``{season: BoxPriorModel}`` from the committed JSON; a model that learned from its own season raises."""
    import numpy as np

    out = {}
    for r in json.loads(Path(path).read_text())["models"]:
        m = BoxPriorModel(
            feature_names=r["feature_names"],
            o_coef=np.asarray(r["o_coef"]),
            o_intercept=np.asarray(r["o_intercept"]),
            d_coef=np.asarray(r["d_coef"]),
            d_intercept=np.asarray(r["d_intercept"]),
            season=int(r["season"]),
            train_seasons=[int(s) for s in r["train_seasons"]],
        )
        if m.season in m.train_seasons:
            raise ValueError(f"the {m.season} box prior learned from its own season")
        out[m.season] = m
    return out


def _height(h: object) -> Optional[float]:
    ft, _, inch = str(h or "").partition("-")
    try:
        return 12.0 * float(ft) + float(inch)
    except ValueError:
        return None


def season_bio(ages: pl.DataFrame, index: pl.DataFrame) -> pl.DataFrame:
    """``player_id, age, height_in, position_num`` from ``nba_player_ages`` and a raw ``playerindex`` frame.

    A player missing from the season's bio stats gets a null age (the prior centres it at 27).
    """
    id_col = "person_id" if "person_id" in index.columns else "player_id"
    static = index.select(
        pl.col(id_col).cast(pl.Int64).alias("player_id"),
        pl.col("height").map_elements(_height, return_dtype=pl.Float64).alias("height_in"),
        pl.col("position")
        .map_elements(_position_to_num, return_dtype=pl.Float64)
        .alias("position_num"),
    ).unique("player_id", keep="first", maintain_order=True)
    return static.join(
        ages.unique("player_id", keep="first"), on="player_id", how="full", coalesce=True
    )


def regular_possessions(poss: pl.DataFrame) -> pl.DataFrame:
    """Regular-season (``002``) possessions with a full lineup and points, ``game_id`` as Utf8."""
    p = poss.with_columns(pl.col("game_id").cast(pl.Utf8))
    return p.filter(pl.col("game_id").str.starts_with("002")).drop_nulls(["points", *_OFF, *_DEF])


def box_prior_columns(
    poss: pl.DataFrame,
    player_logs: pl.DataFrame,
    team_logs: pl.DataFrame,
    bio: pl.DataFrame,
    model: BoxPriorModel,
) -> pl.DataFrame:
    """The BB-D38 columns for one regular season: ``player_id`` + :data:`D38_COLUMNS`."""
    poss = regular_possessions(poss)
    prior = apply_box_prior(box_prior_features(player_logs, team_logs, poss, bio), model)
    pd = {r[0]: (r[1], r[2]) for r in prior.select("player_id", "o_prior", "d_prior").iter_rows()}
    rating = nba_reml_rapm(poss, pd, penalty="fixed", league_id="00")
    return prior.select(
        "player_id",
        pl.col("o_prior").alias("o_box_prior"),
        pl.col("d_prior").alias("d_box_prior"),
        pl.col("box_prior"),
    ).join(
        rating.select("player_id", "o_reml_rapm", "d_reml_rapm", "reml_rapm"),
        on="player_id",
        how="full",
        coalesce=True,
    )


def append_d38(published: pl.DataFrame, built: pl.DataFrame) -> pl.DataFrame:
    """A published ``nba_player_impact`` season with the BB-D38 columns of a rebuild appended last.

    Every published column keeps its values and place (a rebuild alone moves floats by ~1e-14 and can
    flip a tied rank). The rebuild must rate exactly the published players, season type by season type.
    """
    keys = ["player_id", "season_type"]
    if not published.select(keys).sort(keys).equals(built.select(keys).sort(keys)):
        raise ValueError("the rebuild's players differ from the published season's")
    out = published.join(
        built.select(*keys, *D38_COLUMNS), on=keys, how="left", maintain_order="left"
    )
    assert out.height == published.height
    return out


def eval_dates(game_dates: pl.Series) -> list[dt.date]:
    """Opening night, then every :data:`STEP_DAYS` days through the season's last game day."""
    d0, d1 = game_dates.min(), game_dates.max()
    return [d0 + dt.timedelta(days=k) for k in range(0, (d1 - d0).days + 1, STEP_DAYS)]


def build_nba_current_impact(
    seasons: list[int],
    out_dir,
    *,
    compile_season: Callable[[int], pl.DataFrame],
    leaguegamelog: Fetch,
    playerindex: Fetch,
    biostats: Fetch,
    models: Optional[dict[int, BoxPriorModel]] = None,
    start: int = CURRENT_IMPACT_START,
) -> list[dict]:
    """Write ``nba_current_impact_{season}.parquet`` for each season END year in ``seasons``.

    The filter runs over every regular season from :data:`CURRENT_IMPACT_START` to ``max(seasons)``, with a
    window box prior (``current_impact_prior``: the 365 days of box lines before the date, scored with that
    season's BB-D38 model) at each as-of date. A season's file holds its as-of dates (:func:`eval_dates`);
    ``season`` is that season (opening night included) and ``off_poss`` / ``def_poss`` count its
    possessions before the date (0 on opening night), and a player is listed while his last game is
    within :data:`ACTIVE_DAYS` of the date. No uncertainty column: ``nba_current_impact`` exposes no
    posterior variance, and the filter's SD is not validated yet.

    Args:
        seasons: Season END years to write (2026 = 2025-26); each needs a box prior model.
        out_dir: Output directory.
        compile_season: END year -> the season's regular-season possessions (``compile_nba_season``).
        leaguegamelog / playerindex / biostats: The season-level fetches (store-backed in the CLI).
        models: ``{season: BoxPriorModel}``; default :func:`load_box_prior_models`.
        start: The filter's first season (its possessions and box lines are read, plus the box lines
            of the season before it for the window prior).

    Returns:
        ``[{"season", "rows", "path"}]`` per season written.
    """
    models = load_box_prior_models() if models is None else models
    want = sorted(seasons)
    if want[0] < start:
        raise ValueError(f"seasons start at {want[0]}, before the filter's first season {start}")
    run = range(start, want[-1] + 1)
    missing = [s for s in run if s not in models]
    if missing:
        raise ValueError(f"no box prior model for seasons {missing}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def logs(end_year: int) -> tuple[pl.DataFrame, pl.DataFrame]:
        lg = nba_box_logs(
            f"{end_year - 1}-{end_year % 100:02d}",
            season_type="Regular Season",
            fetch=leaguegamelog,
        )
        return lg["player"], lg["team"]

    poss_all, priors, dates = [], [], {}
    prev = None
    for s in run:
        s_str = f"{s - 1}-{s % 100:02d}"
        poss = regular_possessions(compile_season(s)).with_columns(
            pl.lit(s, pl.Int64).alias("season")
        )
        lp, lt = logs(s)
        prev = prev or (regular_possessions(compile_season(s - 1)), *logs(s - 1))
        bio = season_bio(
            nba_player_ages(s_str, fetch=biostats), playerindex(season=s_str, league_id="00")
        )
        cat = [pl.concat([a, b], how="diagonal_relaxed") for a, b in zip(prev, (poss, lp, lt))]
        dates[s] = eval_dates(poss["game_date"])
        for d in dates[s]:
            priors.append(current_impact_prior(cat[1], cat[2], cat[0], bio, models[s], d))
        poss_all.append(poss)
        prev = (poss, lp, lt)
        print(f"current-impact: season={s} poss={poss.height:,} dates={len(dates[s])}", flush=True)

    every = [d for s in want for d in dates[s]]
    cur = nba_current_impact(pl.concat(poss_all, how="diagonal_relaxed"), pl.concat(priors), every)
    results = []
    for s in want:
        f = (
            cur.filter(pl.col("as_of").is_in(dates[s]))
            .filter(pl.col("last_game_date") >= pl.col("as_of") - pl.duration(days=ACTIVE_DAYS))
            # sdv-py's season/possessions are those of the last game before the date: at opening
            # night last season's. Publish the date's own season and its possessions (none yet).
            .with_columns(
                *[
                    pl.when(pl.col("season") == s).then(pl.col(c)).otherwise(0).alias(c)
                    for c in ("off_poss", "def_poss")
                ],
                pl.lit(s, pl.Int64).alias("season"),
            )
        )
        path = out_dir / f"nba_current_impact_{s}.parquet"
        f.write_parquet(path)
        f.write_csv(path.with_suffix(".csv"))
        write_rds(f, path.with_suffix(".rds"), cls=list(RDS_CLASS))
        results.append({"season": s, "rows": f.height, "path": str(path)})
        print(f"current-impact: season={s} rows={f.height} -> {path}", flush=True)
    return results
