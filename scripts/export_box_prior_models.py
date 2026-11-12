"""Export the BB-D38 box prior v2 models into ``models/box_prior_v2.json`` (one record per season).

Reads the ``OUT`` directory of sportsdataverse-py ``tools/fit_box_prior_v2.py`` (``panel`` + ``prior``
stages): ``model_{s}.npz`` for every fitted season. ``--next YEAR`` also fits the prior for a season that
has no box lines yet (the in-progress one): the career target over every fitted season, centred on YEAR,
and the cross-fitted ridge on their ``feat_{s}.parquet`` rows -- exactly the tool's ``_prior_for``, so the
model never reads YEAR. Rerun once a season completes (fit it in the tool, then ``--next`` the new one).

Usage::

    uv run python scripts/export_box_prior_models.py OUT --next 2027
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl
from sportsdataverse.nba.nba_box_prior import (
    BoxPriorModel,
    SeasonGram,
    box_prior_training_seasons,
    career_rapm_target,
    train_box_prior,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from nba_model_publish.prior_informed import MODELS_PATH, model_record  # noqa: E402


def _npz_model(f: Path) -> dict:
    z = np.load(f)
    return model_record(
        BoxPriorModel(
            feature_names=[str(x) for x in z["feature_names"]],
            o_coef=z["o_coef"],
            o_intercept=z["o_intercept"],
            d_coef=z["d_coef"],
            d_intercept=z["d_intercept"],
            season=int(z["season"]),
            train_seasons=[int(x) for x in z["train_seasons"]],
        )
    )


def _gram(f: Path) -> SeasonGram:
    z = np.load(f)
    return SeasonGram(
        pids=z["pids"],
        gram=z["gram"],
        xty=z["xty"],
        counts=z["counts"],
        n=int(z["n"]),
        ysum=float(z["ysum"]),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path, help="fit_box_prior_v2.py OUT directory")
    ap.add_argument("--next", type=int, default=None, help="also fit this not-yet-played season")
    ap.add_argument("--dest", type=Path, default=MODELS_PATH)
    a = ap.parse_args(argv)
    recs = [_npz_model(f) for f in sorted(a.out.glob("model_*.npz"))]
    if not recs:
        raise SystemExit(f"no model_*.npz under {a.out}; {a.dest} left as it is")
    if a.next is not None:
        fitted = [r["season"] for r in recs]
        train = box_prior_training_seasons(a.next, fitted)
        grams = {s: _gram(a.out / f"gram_{s}.npz") for s in train}
        ages = pl.read_parquet(a.out / "ages.parquet")
        target = career_rapm_target(grams, ages, seasons=train, center=a.next)
        pan = pl.concat([pl.read_parquet(a.out / f"feat_{s}.parquet") for s in train]).join(
            target.select("player_id", "season", "o_target", "d_target"),
            on=["player_id", "season"],
            how="inner",
        )
        recs.append(model_record(train_box_prior(pan, season=a.next)))
    recs.sort(key=lambda r: r["season"])
    a.dest.write_text(json.dumps({"models": recs}, indent=1) + "\n")
    print(f"{len(recs)} models ({recs[0]['season']}-{recs[-1]['season']}) -> {a.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
