"""Tests for build.py — mock compile_nba_season, use the real rapm/validate."""
from pathlib import Path

import nba_data_build.build as B
import numpy as np
import polars as pl

_OFF = [f"off_player_{i}" for i in range(1, 6)]
_DEF = [f"def_player_{i}" for i in range(1, 6)]


def _synthetic_season(season: int) -> pl.DataFrame:
    """A tiny 2-team synthetic season: 6 games, 40 possessions each side."""
    rng = np.random.default_rng(season)
    rows = []
    for g in range(6):
        for off_t, ids_o, ids_d in ((100, range(1, 6), range(6, 11)), (200, range(6, 11), range(1, 6))):
            for _ in range(40):
                r = {"game_id": f"{season}{g:04d}", "offense_team_id": off_t, "points": int(rng.integers(0, 3))}
                for i, (o, d) in enumerate(zip(ids_o, ids_d)):
                    r[f"off_player_{i + 1}"] = o
                    r[f"def_player_{i + 1}"] = d
                rows.append(r)
    schema = {
        "game_id": pl.Utf8,
        "offense_team_id": pl.Int64,
        "points": pl.Int64,
        **{c: pl.Int64 for c in _OFF + _DEF},
    }
    return pl.DataFrame(rows, schema=schema)


def test_build_season_produces_possessions_and_rapm(monkeypatch: object) -> None:
    monkeypatch.setattr(B, "compile_nba_season", lambda season, **kw: _synthetic_season(season))
    res = B.build_season(2024)
    assert res.season == 2024 and res.n_possessions == res.possessions.height > 0
    # rapm has RAPM_SCHEMA columns + a season column
    assert {"player_id", "o_rapm", "d_rapm", "rapm", "off_poss", "def_poss", "season"} <= set(res.rapm.columns)
    assert res.rapm["season"].unique().to_list() == [2024]


def test_build_season_passes_end_year_through_with_no_conversion(monkeypatch: object) -> None:
    """Locks in the Task 7 chain unification: build_season's input IS the
    compile_nba_season input verbatim -- no internal ``season + 1``. A stray +1
    was briefly introduced in build_season during this migration and later
    removed; the actual pre-existing off-by-one was most_recent_nba_season()
    (end-year) being fed into a --through slot still documented/treated as
    start-year, fixed by making --through end-year to match rather than by
    adjusting build_season."""
    seen: dict[str, int] = {}

    def _fake_compile(season, **kw):
        seen["season"] = season
        return _synthetic_season(season)

    monkeypatch.setattr(B, "compile_nba_season", _fake_compile)
    res = B.build_season(2026)
    assert seen["season"] == 2026
    assert res.season == 2026


def test_build_writes_artifacts_and_card(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setattr(B, "compile_nba_season", lambda season, **kw: _synthetic_season(season))
    results = B.build([2023, 2024], out_dir=tmp_path)
    assert (tmp_path / "rapm" / "nba_rapm_2024.parquet").exists()
    assert (tmp_path / "possessions" / "nba_possessions_2024.parquet").exists()
    card = tmp_path / "nba_rapm_validation_report.md"
    assert card.exists() and "plain_rapm" in card.read_text(encoding="utf-8")
    assert len(results) == 2
