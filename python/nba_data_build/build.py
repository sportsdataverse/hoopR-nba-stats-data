"""Compile a season, fit RAPM, validate, and write artifacts — reusing the sdv-py harness."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import polars as pl

# NOTE: nba_rapm is NOT re-exported from the sportsdataverse.nba package (verified on
# main) — it lives in the nba_rapm submodule. The other four ARE package-level exports.
from sportsdataverse.nba import RidgeRapmModel, compile_nba_season, render_report, validate_model
from sportsdataverse.nba.nba_rapm import nba_rapm

from .io import write_possessions, write_rapm, write_report


@dataclass(frozen=True)
class BuildResult:
    season: int
    possessions: pl.DataFrame
    rapm: pl.DataFrame
    n_games: int
    n_possessions: int


def build_season(season: int, *, cache_dir: Optional[str] = None) -> BuildResult:
    """Compile one season's possessions (live, cached) and fit its RAPM ratings.

    Args:
        season: Season start-year (e.g. 2023 for 2023-24).
        cache_dir: Optional compile cache dir (forwarded to ``compile_nba_season``).

    Returns:
        A ``BuildResult`` with the possession frame and the season-tagged RAPM frame,
        both tagged with the season end-year (e.g. 2024 for 2023-24).
    """
    season_end = season + 1
    poss = compile_nba_season(season_end, cache_dir=cache_dir)
    ratings = nba_rapm(poss).with_columns(pl.lit(season_end, dtype=pl.Int64).alias("season"))
    n_games = poss["game_id"].n_unique() if not poss.is_empty() else 0
    return BuildResult(season=season_end, possessions=poss, rapm=ratings,
                       n_games=n_games, n_possessions=poss.height)


def build(seasons: list[int], out_dir: Path, *, cache_dir: Optional[str] = None) -> list[BuildResult]:
    """Build each season, write its parquet, then write the pooled validation card.

    Writes ``out_dir/possessions/nba_possessions_{season_end}.parquet``,
    ``out_dir/rapm/nba_rapm_{season_end}.parquet``, and
    ``out_dir/nba_rapm_validation_report.md``.

    Args:
        seasons: List of season start-years to build (e.g. [2022, 2023]).
        out_dir: Root output directory for all artifacts.
        cache_dir: Optional compile cache dir (forwarded to ``compile_nba_season``).

    Returns:
        A list of ``BuildResult`` instances, one per season (``season`` end-year tagged).
    """
    out_dir = Path(out_dir)
    results: list[BuildResult] = []
    for season in seasons:
        res = build_season(season, cache_dir=cache_dir)
        write_possessions(res.possessions, out_dir / "possessions" / f"nba_possessions_{res.season}.parquet")
        write_rapm(res.rapm, out_dir / "rapm" / f"nba_rapm_{res.season}.parquet")
        results.append(res)
    if results:
        report = validate_model(RidgeRapmModel(), [r.possessions for r in results],
                                model_name="plain_rapm")
        write_report(render_report(report), out_dir / "nba_rapm_validation_report.md")
    return results
