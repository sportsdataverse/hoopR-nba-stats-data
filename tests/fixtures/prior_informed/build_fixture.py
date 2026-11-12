"""Rebuild the ``prior_informed`` fixture (real data; rows filtered, columns dropped, nothing edited).

Usage (local raw store + possession cache, and a sportsdataverse-py ``tools/fit_box_prior_v2.py`` OUT)::

    uv run python tests/fixtures/prior_informed/build_fixture.py RAW_STORE_JSON D38_OUT
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import polars as pl
from sportsdataverse.nba import compile_nba_season
from sportsdataverse.nba.nba_stats import (
    nba_stats_leaguedashplayerbiostats,
    nba_stats_leaguegamelog,
    nba_stats_playerindex,
)

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[2] / "python"))
from nba_model_publish.builders import _store_backed  # noqa: E402

_LINEUP = [f"{s}_player_{i}" for s in ("off", "def") for i in range(1, 6)]
KEEP = ["game_id", "game_date", "season", "points", "offense_team_id", "defense_team_id", *_LINEUP]
#: 2013-14 from this date and 2014-15 before CUT_2015: the window prior at 2014-10-28 / 11-04.
FROM_2014, CUT_2015 = dt.date(2014, 4, 1), dt.date(2014, 11, 8)


def main(raw: str, d38: str) -> None:
    lg = _store_backed("leaguegamelog", nba_stats_leaguegamelog, None, raw, False)
    idx = _store_backed("playerindex", nba_stats_playerindex, None, raw, False)
    bio = _store_backed(
        "leaguedashplayerbiostats", nba_stats_leaguedashplayerbiostats, None, raw, False
    )
    keep = {2014: pl.col("game_date") >= FROM_2014, 2015: pl.col("game_date") < CUT_2015}
    poss, logs = [], []
    for s, cond in keep.items():
        p = compile_nba_season(
            s, season_type="Regular Season", lineup_source="auto", raw_store_dir=raw,
            raw_store_readonly=True, delay_s=0.0,
        ).filter(cond)  # fmt: skip
        poss.append(p.select(KEEP))
        gids = p["game_id"].unique().to_list()
        for pt in ("P", "T"):
            f = lg(season=f"{s - 1}-{s % 100:02d}", player_or_team_abbreviation=pt)
            gcol = "game_id" if "game_id" in f.columns else "GAME_ID"
            logs.append(f.filter(pl.col(gcol).is_in(gids)).with_columns(
                pl.lit(s).alias("_season"), pl.lit(pt).alias("_pt")))  # fmt: skip
    pl.concat(poss).write_parquet(HERE / "possessions_2014_2015.parquet", compression_level=19)
    pl.concat(logs, how="diagonal_relaxed").write_parquet(
        HERE / "leaguegamelog_2014_2015.parquet", compression_level=19
    )
    players = pl.concat(poss).select(pl.concat_list(_LINEUP).explode().unique().alias("pid"))
    pids = players["pid"].to_list()
    ix = idx(season="2014-15", league_id="00")
    ix.filter(pl.col("person_id").cast(pl.Int64).is_in(pids)).write_parquet(
        HERE / "playerindex_2015.parquet"
    )
    b = bio(season="2014-15", league_id="00")
    b.filter(pl.col("player_id").cast(pl.Int64).is_in(pids)).write_parquet(
        HERE / "biostats_2015.parquet"
    )
    # The D38 fit's own features and priors (its OUT), 40 players per season: the JSON models must
    # reproduce the priors the fit wrote.
    rows = []
    for s in (2004, 2010, 2024):
        f = pl.read_parquet(f"{d38}/feat_{s}.parquet").sort("poss", descending=True).head(40)
        pr = pl.read_parquet(f"{d38}/prior_{s}.parquet").select("player_id", "o_prior", "d_prior")
        rows.append(f.join(pr, on="player_id", how="inner"))
    pl.concat(rows).write_parquet(HERE / "d38_fit_features_priors.parquet")


if __name__ == "__main__":
    main(*sys.argv[1:3])
