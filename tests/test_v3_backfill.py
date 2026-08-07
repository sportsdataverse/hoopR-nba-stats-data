"""Offline unit tests for the Program V backfill: gamelog pivot + checkpoint/resume."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from nba_data_build import v3_backfill as vb


def _write_gamelog(raw_root: Path, start_year: int, variant: str, rows: list[list]) -> None:
    headers = [
        "SEASON_ID",
        "TEAM_ID",
        "TEAM_ABBREVIATION",
        "TEAM_NAME",
        "GAME_ID",
        "GAME_DATE",
        "MATCHUP",
        "WL",
        "PTS",
    ]
    d = raw_root / "nba_stats" / "json" / "leaguegamelog" / str(start_year)
    d.mkdir(parents=True, exist_ok=True)
    payload = {"resultSets": [{"name": "LeagueGameLog", "headers": headers, "rowSet": rows}]}
    (d / f"{variant}.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture()
def raw_root(tmp_path: Path) -> Path:
    root = tmp_path / "raw"
    _write_gamelog(
        root,
        2005,
        "regular-season",
        [
            ["22005", 1, "AAA", "Alphas", "0020500001", "2005-11-01", "AAA vs. BBB", "W", 101],
            ["22005", 2, "BBB", "Betas", "0020500001", "2005-11-01", "BBB @ AAA", "L", 99],
        ],
    )
    _write_gamelog(
        root,
        2005,
        "playoffs",
        [
            ["42005", 1, "AAA", "Alphas", "0040500001", "2006-04-20", "AAA vs. BBB", "L", 88],
            ["42005", 2, "BBB", "Betas", "0040500001", "2006-04-20", "BBB @ AAA", "W", 90],
        ],
    )
    return root


def test_schedule_from_gamelog_pivots_home_away(raw_root: Path) -> None:
    df = vb.schedule_from_gamelog(raw_root, 2006)
    assert df.height == 2
    assert df.schema["game_id"] == pl.Utf8
    reg = df.filter(pl.col("game_id") == "0020500001").row(0, named=True)
    assert reg["home_team_abbreviation"] == "AAA"
    assert reg["home_pts"] == 101 and reg["away_pts"] == 99
    assert reg["season"] == 2006 and reg["season_type"] == "regular-season"
    po = df.filter(pl.col("game_id") == "0040500001").row(0, named=True)
    assert po["season_type"] == "playoffs" and po["home_wl"] == "L"


def test_schedule_from_gamelog_empty_when_uncaptured(tmp_path: Path) -> None:
    df = vb.schedule_from_gamelog(tmp_path, 2006)
    assert df.height == 0
    assert set(vb._SCHEDULE_SCHEMA) == set(df.columns)


def test_season_done_checkpoint(tmp_path: Path) -> None:
    staging = tmp_path / "v3_staging"
    assert not vb.season_done(staging, 2006)
    staging.mkdir()
    paths = vb.season_paths(staging, 2006)
    assert paths["schedule"].name == "nba_schedule_2006.parquet"
    assert paths["play_by_play"].name == "nba_play_by_play_2006.parquet"
    for p in paths.values():
        p.touch()
    assert vb.season_done(staging, 2006)


def test_build_season_skips_when_done(tmp_path: Path, raw_root: Path) -> None:
    staging = tmp_path / "v3_staging"
    staging.mkdir()
    for p in vb.season_paths(staging, 2006).values():
        p.touch()
    out = vb.build_season(raw_root, 2006, staging, tmp_path / "cache")
    assert out == {"season": 2006, "status": "skipped"}


def test_build_season_uncaptured_games_dont_fail(tmp_path: Path, raw_root: Path) -> None:
    # No per-game pbp captures exist in the fixture store: build still writes the
    # schedule + empty frames and reports the games as uncaptured.
    staging = tmp_path / "v3_staging"
    out = vb.build_season(raw_root, 2006, staging, tmp_path / "cache")
    assert out["status"] == "built"
    assert out["games_indexed"] == 2
    assert out["games_uncaptured"] == 2
    assert out["games_processed"] == 0
    assert out["rows"]["schedule"] == 2
    sched = pl.read_parquet(vb.season_paths(staging, 2006)["schedule"])
    assert sched["game_id"].to_list() == ["0020500001", "0040500001"]
    # Checkpoint now holds: a rerun skips.
    assert vb.build_season(raw_root, 2006, staging, tmp_path / "cache")["status"] == "skipped"
