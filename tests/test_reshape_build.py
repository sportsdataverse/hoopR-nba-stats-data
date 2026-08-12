"""Builder tests for the NBA reshaper.

Synthetic payloads for the unit cases; the real-store cases read the sibling
``hoopR-nba-stats-raw`` checkout and skip when it is absent. Ported from the WNBA
reshaper's ``test_build.py`` — the v3 nesting is identical, so the extractors and
their tests port over; the real-store seasons are NBA ones (2013, well-covered per
``docs/nba-v3-coverage.md``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nba_data_build.reshape import build
from nba_data_build.reshape.datasets import BY_KEY

REAL = Path("/mnt/sdv_repos/hoopR-nba-stats-raw/nba_stats/json")
needs_real = pytest.mark.skipif(not REAL.is_dir(), reason="no sibling raw checkout")


def _write(root: Path, rel: str, payload: object) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")


def _rs(headers, rows, name="X"):
    return {"resultSets": [{"name": name, "headers": headers, "rowSet": rows}]}


# -- column naming -------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_name,expected",
    [
        ("TEAM_ID", "team_id"),
        ("PLAYER_NAME", "player_name"),
        ("teamId", "team_id"),
        ("isFieldGoal", "is_field_goal"),
        # trailing acronyms: a naive split-before-capital yields league_i_d, and
        # these are join keys -- a mangled name breaks joins silently downstream
        ("LeagueID", "league_id"),
        ("SeasonID", "season_id"),
    ],
)
def test_snake(raw_name: str, expected: str) -> None:
    assert build.snake(raw_name) == expected


# -- frames --------------------------------------------------------------------


def test_frame_from_result_set_adds_extras() -> None:
    df = build.frame_from_result_set(["TEAM_ID", "W"], [[1, 2], [3, 4]], {"season": 2013})
    assert df.columns == ["team_id", "w", "season"]
    assert df.height == 2 and df["season"].to_list() == [2013, 2013]


def test_empty_result_set_is_an_empty_frame() -> None:
    assert build.frame_from_result_set([], []).height == 0


def test_variant_columns_carry_the_parameters() -> None:
    assert build._variant_columns("regular-season_base_totals") == {
        "season_type": "regular-season",
        "measure_type": "base",
        "per_mode": "totals",
    }
    assert build._variant_columns(None) == {}


# -- season datasets -----------------------------------------------------------


def test_season_dataset_reads_the_unparameterized_form(tmp_path: Path) -> None:
    _write(tmp_path, "leaguestandingsv3/2013.json", _rs(["TEAM_ID"], [[1]]))
    assert build.build_season_dataset(tmp_path, BY_KEY["standings"], 2013).height == 1


def test_derived_dataset_refuses_the_generic_builder() -> None:
    with pytest.raises(ValueError, match="derived"):
        build.build_season_dataset("/tmp", BY_KEY["shots"], 2013)


# -- against the real store ----------------------------------------------------


@needs_real
def test_standings_from_real_store() -> None:
    df = build.build(REAL, BY_KEY["standings"], 2013)
    assert df.height > 0, "standings built empty from the real store"
    assert not [c for c in df.columns if "_i_d" in c], df.columns
    assert "season" in df.columns
    assert df["season"].unique().to_list() == [2013]  # START year


@needs_real
def test_player_season_stats_from_real_store() -> None:
    df = build.build(REAL, BY_KEY["player_season_stats"], 2013)
    assert df.height > 0, "player_season_stats built empty from the real store"
    assert not [c for c in df.columns if "_i_d" in c], df.columns


@needs_real
def test_game_rosters_from_real_store() -> None:
    """boxscoresummaryv2 resultSets path (InactivePlayers)."""
    df = build.build(REAL, BY_KEY["game_rosters"], 2013)
    assert df.height > 0, "game_rosters built empty from the real store"
    assert {"game_id", "season"} <= set(df.columns)


@needs_real
def test_pbp_from_real_store() -> None:
    df = build.build_pbp(REAL, 2013)
    assert df.height > 0, "pbp built empty from the real store"
    assert {"game_id", "season"} <= set(df.columns)
    # game_id stays a zero-padded 10-char Utf8 id, never a float cast
    assert df.schema["game_id"] == build.pl.Utf8
    assert all(len(g) == 10 for g in df["game_id"].unique().to_list())


@needs_real
@pytest.mark.parametrize("team_level", [False, True])
def test_boxscores_from_real_store(team_level: bool) -> None:
    df = build.build_boxscores(REAL, 2013, team_level=team_level)
    assert df.height > 0, f"boxscores(team_level={team_level}) built empty"
    assert {"game_id", "season", "team_id"} <= set(df.columns)


@needs_real
def test_shots_derived_from_real_pbp() -> None:
    shots = build.build_shots(build.build_pbp(REAL, 2013))
    assert shots.height > 0, "shots derived empty from real pbp"
    # every retained row is a field-goal action
    assert "is_field_goal" not in shots.columns  # filtered, not carried
    assert {"shot_result", "shot_value", "shot_distance"} <= set(shots.columns)


@needs_real
def test_draft_builds_from_the_real_store() -> None:
    """draft routes through build_season_dataset (endpoint ``drafthistory``).

    The 2013 draft is 60 picks over two rounds. Asserting the count rather than
    just non-emptiness is deliberate: an unfiltered drafthistory call answers
    with the FULL 1947-2026 history, so a season that silently lost its season
    filter would still be "non-empty" — it would just be wrong.
    """
    df = build.build(REAL, BY_KEY["draft"], 2013)
    assert df.height == 60, f"2013 draft built {df.height} rows, expected 60"
    assert set(df["season"].unique().to_list()) == {2013}
    assert sorted(df["round_number"].unique().to_list()) == [1, 2]
