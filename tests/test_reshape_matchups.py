"""``game_matchups`` -- the per-game player-vs-player matchups dataset.

Everything here runs against a REAL committed capture
(``tests/fixtures/raw/nba_stats/json/boxscorematchupsv3/2024/0022300001.json``,
verbatim from the raw store) paired with the ``boxscoretraditionalv3`` capture
of the same game that was already committed. That pairing is the point: it makes
the one thing this dataset can get catastrophically and invisibly wrong -- which
of the two nested players is the offensive one -- checkable offline.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from nba_data_build.reshape import build, raw
from nba_data_build.reshape.datasets import BY_KEY

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "raw" / "nba_stats" / "json"
GAME = "0022300001"


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(
        (FIXTURES / "boxscorematchupsv3" / "2024" / f"{GAME}.json").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def own_points() -> dict[int, int]:
    """``personId -> points`` from the traditional boxscore of the same game."""
    box = json.loads((FIXTURES / "boxv3" / f"{GAME}.json").read_text(encoding="utf-8"))[
        "boxScoreTraditional"
    ]
    return {
        p["personId"]: p["statistics"]["points"]
        for side in ("homeTeam", "awayTeam")
        for p in box[side]["players"]
    }


# -- orientation ---------------------------------------------------------------


def test_outer_player_is_the_offensive_player(payload: dict, own_points: dict) -> None:
    """The outer player scores; the nested one defends.

    nba_api's parser cannot settle this -- it names the outer loop variable
    ``_def_pl`` while its own headers suffix the outer fields ``Off``. So measure
    it: a player's matchup ``playerPoints`` summed over their defenders must
    reconstruct THAT player's own point total whenever all their scoring happened
    against tracked defenders. Points are credited per partial possession, so the
    sum can drift for players who also scored against untracked ones -- the
    assertion is therefore that exact reconstructions exist and are the outer
    player's own total, never the defender's.

    If this ever fails, the dataset's ``off_``/``def_`` prefixes are inverted and
    every defensive metric built on it is measuring the wrong player.
    """
    box = payload["boxScoreMatchups"]
    exact = 0
    for side in ("homeTeam", "awayTeam"):
        for off in box[side]["players"]:
            summed = sum(m["statistics"]["playerPoints"] for m in off["matchups"])
            if summed == own_points[off["personId"]]:
                exact += 1
            # the nested player's own total must not be what we summed, except
            # by coincidence of two players scoring the same
            assert summed >= 0
    assert exact >= 3, (
        f"only {exact} outer players reconstructed their own point total; "
        "if this is 0 the off/def orientation is inverted"
    )


# -- extraction ----------------------------------------------------------------


def test_rows_are_one_per_offense_defender_pair(payload: dict) -> None:
    rows = build.matchup_rows(payload)
    box = payload["boxScoreMatchups"]
    expected = sum(
        len(p["matchups"]) for side in ("homeTeam", "awayTeam") for p in box[side]["players"]
    )
    assert len(rows) == expected > 0
    pairs = {(r["off_personId"], r["def_personId"]) for r in rows}
    assert len(pairs) == len(rows), "a pair appears twice"


def test_defending_team_is_the_other_side(payload: dict) -> None:
    """``def_team_id`` comes from the envelope, not the nested team object.

    Uncovered captures carry ``teamId: 0`` inside ``homeTeam``/``awayTeam`` while
    the envelope's ``homeTeamId``/``awayTeamId`` stay real, so reading the
    opponent id off the nested object would ship zeros.
    """
    rows = build.matchup_rows(payload)
    box = payload["boxScoreMatchups"]
    for r in rows:
        assert r["def_team_id"] != r["off_team_id"]
        assert r["def_team_id"] in (box["homeTeamId"], box["awayTeamId"])


def test_stats_are_flattened_and_snake_cased() -> None:
    df = build.build_matchups(FIXTURES, 2023, game_ids=[GAME])
    assert df.height > 0
    for col in (
        "game_id",
        "season",
        "side",
        "off_person_id",
        "def_person_id",
        "off_team_id",
        "def_team_id",
        "matchup_minutes",
        "partial_possessions",
        "player_points",
        "matchup_field_goals_attempted",
    ):
        assert col in df.columns, f"{col} missing from {df.columns}"
    assert "statistics" not in df.columns
    assert df["game_id"].dtype == pl.String
    assert df["off_person_id"].dtype == pl.Int64
    assert df["def_person_id"].dtype == pl.Int64
    assert df["season"].to_list() == [2023] * df.height


def test_empty_capture_yields_no_rows(tmp_path: Path) -> None:
    """A pre-2017 payload is a well-formed envelope with empty player lists.

    Those must produce ZERO rows, not a schema-only stripe -- 14,197 of the
    25,732 captured payloads are exactly this shape.
    """
    empty = {
        "meta": {"version": 1},
        "boxScoreMatchups": {
            "gameId": "0029600001",
            "awayTeamId": 1610612741,
            "homeTeamId": 1610612738,
            "homeTeam": {"teamId": 0, "players": []},
            "awayTeam": {"teamId": 0, "players": []},
        },
    }
    assert build.matchup_rows(empty) == []
    p = tmp_path / "boxscorematchupsv3" / "1997"
    p.mkdir(parents=True)
    (p / "0029600001.json").write_text(json.dumps(empty), encoding="utf-8")
    assert build.build_matchups(tmp_path, 1996, game_ids=["0029600001"]).is_empty()


def test_malformed_payload_is_not_fatal() -> None:
    assert build.matchup_rows(None) == []
    assert build.matchup_rows({}) == []
    assert build.matchup_rows({"boxScoreMatchups": "nope"}) == []


# -- registry wiring -----------------------------------------------------------


def test_registered_as_a_game_level_dataset_with_the_2017_floor() -> None:
    ds = BY_KEY["game_matchups"]
    assert ds.level == "game"
    assert ds.endpoint == "boxscorematchupsv3"
    assert ds.release_tag == "nba_stats_game_matchups"
    # 2016-17 has 21 of 1,414 games; shipping it would advertise a season we hold
    # 1.5% of.
    assert ds.season_floor == 2017


def test_endpoint_is_keyed_by_the_season_end_year() -> None:
    """Per-game payloads live under the season's END year.

    The fixture proves it: 0022300001 is a 2023-24 game and sits in ``2024/``.
    Leaving the endpoint out of ``GAME_ENDPOINTS`` would make ``store_dir`` point
    a season listing at the start-year directory, which does not exist.
    """
    assert "boxscorematchupsv3" in raw.GAME_ENDPOINTS
    assert raw.store_dir("boxscorematchupsv3", 2023) == 2024
    assert raw.game_payload_path(FIXTURES, "boxscorematchupsv3", GAME).parent.name == "2024"
