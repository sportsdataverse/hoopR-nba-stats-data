"""Offline unit tests for the Program V backfill: gamelog pivot + checkpoint/resume."""

from __future__ import annotations

import json
import shutil
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


#: Real neutral-site games (both leaguegamelog rows read ``TEAM @ OPP``), with the
#: official home side taken from the committed boxscoretraditionalv3 slices.
#: game_id -> (home_abbr, home_pts, away_abbr, away_pts)
_NEUTRAL_SITE = {
    "0022400147": ("WAS", 98, "MIA", 118),  # Mexico City Game 2024
    "0022401230": ("OKC", 111, "HOU", 96),  # NBA Cup final, Las Vegas
}

FIXTURE_RAW = Path(__file__).parent / "fixtures" / "raw"


def test_schedule_from_gamelog_neutral_site_keeps_both_sides() -> None:
    """Regression: ``@``-on-both-rows games used to null out the whole home side."""
    df = vb.schedule_from_gamelog(FIXTURE_RAW, 2025)
    assert df.filter(pl.col("home_pts").is_null() | pl.col("away_pts").is_null()).is_empty()
    for gid, (h_abbr, h_pts, a_abbr, a_pts) in _NEUTRAL_SITE.items():
        row = df.filter(pl.col("game_id") == gid).row(0, named=True)
        assert (row["home_team_abbreviation"], row["home_pts"]) == (h_abbr, h_pts)
        assert (row["away_team_abbreviation"], row["away_pts"]) == (a_abbr, a_pts)
    control = df.filter(pl.col("game_id") == "0022400001").row(0, named=True)
    assert control["home_team_abbreviation"] == "BOS"
    assert control["matchup"] == "BOS vs. ATL"


def test_schedule_from_gamelog_neutral_site_without_boxscore(tmp_path: Path) -> None:
    """No boxscore to disambiguate still beats dropping a team off the game."""
    src = FIXTURE_RAW / "nba_stats" / "json" / "leaguegamelog" / "2024"
    dst = tmp_path / "nba_stats" / "json" / "leaguegamelog" / "2024"
    dst.mkdir(parents=True)
    shutil.copy(src / "regular-season.json", dst / "regular-season.json")
    df = vb.schedule_from_gamelog(tmp_path, 2025)
    row = df.filter(pl.col("game_id") == "0022400147").row(0, named=True)
    assert row["home_team_abbreviation"] is not None
    assert {row["home_team_abbreviation"], row["away_team_abbreviation"]} == {
        "WAS",
        "MIA",
    }


def _write_league_schedule(raw_root: Path, start_year: int, games: list[dict]) -> None:
    d = raw_root / "nba_stats" / "json" / "scheduleleaguev2"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{start_year}.json").write_text(
        json.dumps({"leagueSchedule": {"gameDates": [{"games": games}]}}), encoding="utf-8"
    )


def _game(gid: str, status: int, h_score: int = 0, a_score: int = 0) -> dict:
    return {
        "gameId": gid,
        "gameStatus": status,
        "gameDateEst": "2005-10-08T00:00:00Z",
        "homeTeam": {
            "teamId": 1,
            "teamTricode": "AAA",
            "teamCity": "Alpha",
            "teamName": "Alphas",
            "score": h_score,
        },
        "awayTeam": {
            "teamId": 2,
            "teamTricode": "BBB",
            "teamCity": "Beta",
            "teamName": "Betas",
            "score": a_score,
        },
    }


def _game_without_scores(gid: str, status: int) -> dict:
    """A payload row that omits ``score`` entirely on both sides."""
    g = _game(gid, status)
    g["homeTeam"].pop("score")
    g["awayTeam"].pop("score")
    return g


def test_season_schedule_adds_non_gamelog_game_types(raw_root: Path) -> None:
    """Preseason / All-Star / play-in / NBA Cup reach the universe via scheduleleaguev2."""
    _write_league_schedule(
        raw_root,
        2005,
        [
            _game("0010500001", 3, 90, 88),  # preseason
            _game("0020500001", 3, 1, 2),  # already in the gamelog -- must NOT override
            _game("0030500001", 3, 120, 119),  # all-star
            _game("0050500001", 3, 100, 95),  # play-in
            _game("0060500001", 3, 111, 96),  # NBA Cup final
            _game("0010500002", 1),  # scheduled, never played
            _game("0010500003", 3),  # "Final" at 0-0 -- cancelled / unscored
            _game_without_scores("0010500004", 3),  # "Final" with no score key at all
            _game("0090500001", 0),  # arena hold, not a game -- must be dropped
        ],
    )
    df = vb.season_schedule(raw_root, 2006)
    assert df["game_id"].to_list() == sorted(df["game_id"].to_list())
    # strict superset of the gamelog-only universe
    assert set(vb.schedule_from_gamelog(raw_root, 2006)["game_id"]) <= set(df["game_id"])
    assert dict(zip(df["game_id"], df["season_type"])) == {
        "0010500001": "preseason",
        "0010500002": "preseason",
        "0010500003": "preseason",
        "0010500004": "preseason",
        "0020500001": "regular-season",
        "0030500001": "all-star",
        "0040500001": "playoffs",
        "0050500001": "play-in",
        "0060500001": "nba-cup",
    }
    # the gamelog row wins where both sources have the game
    assert df.filter(pl.col("game_id") == "0020500001").row(0, named=True)["home_pts"] == 101
    cup = df.filter(pl.col("game_id") == "0060500001").row(0, named=True)
    assert (cup["home_pts"], cup["home_wl"], cup["away_wl"]) == (111, "W", "L")
    assert cup["home_team_name"] == "Alpha Alphas" and cup["matchup"] == "AAA vs. BBB"
    assert cup["season"] == 2006 and cup["game_date"] == "2005-10-08"
    # a scheduled-but-unplayed game carries no fabricated 0-0
    unplayed = df.filter(pl.col("game_id") == "0010500002").row(0, named=True)
    assert unplayed["home_pts"] is None and unplayed["home_wl"] is None
    # a 0-0 "Final" (cancellation / unscored row) must not invent a loser
    tied = df.filter(pl.col("game_id") == "0010500003").row(0, named=True)
    assert tied["home_wl"] is None and tied["away_wl"] is None
    # an absent score stays null rather than becoming a fabricated 0
    unscored = df.filter(pl.col("game_id") == "0010500004").row(0, named=True)
    assert unscored["home_pts"] is None and unscored["away_pts"] is None


def test_season_schedule_falls_back_to_gamelog_when_uncaptured(raw_root: Path) -> None:
    """No scheduleleaguev2 payload -> unchanged pre-existing behavior."""
    df = vb.season_schedule(raw_root, 2006)
    assert df["game_id"].to_list() == ["0020500001", "0040500001"]


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
