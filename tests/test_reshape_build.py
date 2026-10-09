"""Builder tests for the NBA reshaper.

Synthetic payloads for the unit cases; the real-store cases read the sibling
``hoopR-nba-stats-raw`` checkout and skip when it is absent. Ported from the WNBA
reshaper's ``test_build.py`` — the v3 nesting is identical, so the extractors and
their tests port over; the real-store seasons are NBA ones (2014 = 2013-14, well-covered per
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
    _write(tmp_path, "leaguestandingsv3/2014.json", _rs(["TEAM_ID"], [[1]]))
    assert build.build_season_dataset(tmp_path, BY_KEY["standings"], 2014).height == 1


def test_derived_dataset_refuses_the_generic_builder() -> None:
    with pytest.raises(ValueError, match="derived"):
        build.build_season_dataset("/tmp", BY_KEY["shots"], 2014)


# -- against the real store ----------------------------------------------------


@needs_real
def test_standings_from_real_store() -> None:
    df = build.build(REAL, BY_KEY["standings"], 2014)
    assert df.height > 0, "standings built empty from the real store"
    assert not [c for c in df.columns if "_i_d" in c], df.columns
    assert "season" in df.columns
    assert df["season"].unique().to_list() == [2014]  # END year (2013-14)


@needs_real
def test_player_season_stats_from_real_store() -> None:
    df = build.build(REAL, BY_KEY["player_season_stats"], 2014)
    assert df.height > 0, "player_season_stats built empty from the real store"
    assert not [c for c in df.columns if "_i_d" in c], df.columns


@needs_real
def test_game_rosters_from_real_store() -> None:
    """boxscoresummaryv2 resultSets path (InactivePlayers)."""
    df = build.build(REAL, BY_KEY["game_rosters"], 2014)
    assert df.height > 0, "game_rosters built empty from the real store"
    assert {"game_id", "season"} <= set(df.columns)


@needs_real
def test_pbp_from_real_store() -> None:
    df = build.build_pbp(REAL, 2014)
    assert df.height > 0, "pbp built empty from the real store"
    assert {"game_id", "season"} <= set(df.columns)
    # game_id stays a zero-padded 10-char Utf8 id, never a float cast
    assert df.schema["game_id"] == build.pl.Utf8
    assert all(len(g) == 10 for g in df["game_id"].unique().to_list())


@needs_real
@pytest.mark.parametrize("team_level", [False, True])
def test_boxscores_from_real_store(team_level: bool) -> None:
    df = build.build_boxscores(REAL, 2014, team_level=team_level)
    assert df.height > 0, f"boxscores(team_level={team_level}) built empty"
    assert {"game_id", "season", "team_id"} <= set(df.columns)


@needs_real
def test_shots_derived_from_real_pbp() -> None:
    shots = build.build_shots(build.build_pbp(REAL, 2014))
    assert shots.height > 0, "shots derived empty from real pbp"
    # every retained row is a field-goal action
    assert "is_field_goal" not in shots.columns  # filtered, not carried
    assert {"shot_result", "shot_value", "shot_distance"} <= set(shots.columns)


@needs_real
def test_draft_builds_from_the_real_store() -> None:
    """draft routes through build_season_dataset (endpoint ``drafthistory``).

    The 2013 draft (it feeds 2013-14, END year 2014) is 60 picks over two rounds.
    Asserting the count rather than just non-emptiness is deliberate: an unfiltered drafthistory call answers
    with the FULL 1947-2026 history, so a season that silently lost its season
    filter would still be "non-empty" — it would just be wrong.
    """
    df = build.build(REAL, BY_KEY["draft"], 2014)
    assert df.height == 60, f"2013 draft built {df.height} rows, expected 60"
    assert set(df["season"].unique().to_list()) == {2014}
    assert sorted(df["round_number"].unique().to_list()) == [1, 2]


def test_summary_datasets_prefer_v3_and_keep_the_v2_columns(tmp_path: Path) -> None:
    """boxscoresummaryv2 went blank from mid-2024-25: a game with a v3 capture reads
    v3 (re-shaped to the v2 columns); a game with only v2 keeps reading v2."""
    v2_off = {
        "resultSets": [
            {
                "name": "Officials",
                "headers": ["OFFICIAL_ID", "FIRST_NAME", "LAST_NAME", "JERSEY_NUM"],
                "rowSet": [[101283, "Brian", "Forte", "45  "]],
            }
        ]
    }
    v3 = {
        "boxScoreSummary": {
            "officials": [
                {"personId": 2882, "firstName": "Sean", "familyName": "Wright", "jerseyNum": "4   "}
            ],
            "awayTeam": {
                "teamId": 1,
                "teamCity": "San Antonio",
                "teamName": "Spurs",
                "teamTricode": "SAS",
                "inactives": [
                    {"personId": 7, "firstName": "A", "familyName": "B", "jerseyNum": "9   "}
                ],
            },
            "homeTeam": {
                "teamId": 2,
                "teamCity": "Oklahoma City",
                "teamName": "Thunder",
                "teamTricode": "OKC",
                "inactives": [],
            },
        }
    }
    _write(tmp_path, "boxscoresummaryv2/2026/0022500001.json", v2_off)
    _write(tmp_path, "boxscoresummaryv2/2026/0052500101.json", {"resultSets": []})  # blank v2 shell
    _write(tmp_path, "boxscoresummaryv3/2026/0052500101.json", v3)
    ids = ["0022500001", "0052500101"]

    off = build.build_game_dataset(tmp_path, BY_KEY["officials"], 2026, ids)
    assert off.select(
        "official_id", "last_name", "jersey_num", "game_id", "season_type_id"
    ).rows() == [
        (101283, "Forte", "45  ", "0022500001", "2"),
        (2882, "Wright", "4   ", "0052500101", "5"),
    ]
    rost = build.build_game_dataset(tmp_path, BY_KEY["game_rosters"], 2026, ids)
    assert rost.select("player_id", "team_abbreviation", "game_id").rows() == [
        (7, "SAS", "0052500101")
    ]


# -- shots: the masked corner-three distance -------------------------------------

SHOTS_FIX = Path(__file__).parent / "fixtures" / "shots"


def _legacy_ft() -> build.pl.Expr:
    """Exact distance in feet: legacy coordinates are tenths of a foot, hoop at the origin."""
    pl = build.pl
    return (
        pl.col("x_legacy").cast(pl.Float64) ** 2 + pl.col("y_legacy").cast(pl.Float64) ** 2
    ).sqrt() / 10


def test_shots_restore_the_masked_three_distance_from_legacy_coordinates() -> None:
    """playbyplayv3 ships ``shotDistance`` 0 for every three under 23.5 ft (the
    corner); shotchartdetail ships the real distance for the same shots. Real
    2025-26 opener (OKC-HOU) slice: 22 such threes, all corner, all 0 in the raw."""
    pl = build.pl
    raw = build.build_pbp(SHOTS_FIX, 2026, ["0022500001"])
    raw3 = raw.filter(pl.col("is_field_goal") == 1, pl.col("shot_value") == 3)
    assert raw3.filter(pl.col("shot_distance") == 0).height == 22, "fixture lost its masked threes"

    shots = build.build_shots(raw).with_columns(loc=_legacy_ft())
    threes = shots.filter(pl.col("shot_value") == 3)
    assert threes.filter(pl.col("shot_distance") == 0).height == 0, "a three still reads 0 ft"
    # The feed's own rule on every unmasked shot: whole feet, half up, from the legacy
    # coordinates. Restored threes follow it, and unmasked shots are untouched.
    assert (
        shots["shot_distance"].to_list()
        == shots.select((pl.col("loc") + 0.5).floor().cast(pl.Int64))["loc"].to_list()
    )
    assert shots.schema["shot_distance"] == raw.schema["shot_distance"]
    assert sorted(set(threes.filter(pl.col("loc") < 23.5)["shot_distance"].to_list())) == [22, 23]

    # Ground truth: shotchartdetail's SHOT_DISTANCE for the same events is the floor of
    # the same coordinates (LOC_X/LOC_Y == xLegacy/yLegacy), so it is 0 or 1 ft under ours.
    scd = json.loads((SHOTS_FIX / "shotchartdetail_0022500001.json").read_text(encoding="utf-8"))
    rs = scd["resultSets"][0]
    truth = pl.DataFrame([dict(zip(rs["headers"], r)) for r in rs["rowSet"]]).select(
        pl.col("GAME_EVENT_ID").alias("action_number"), "SHOT_DISTANCE", "SHOT_ZONE_BASIC"
    )
    events = raw.filter(pl.col("is_field_goal") == 1)[
        "action_number"
    ]  # build_shots keeps row order
    j = shots.with_columns(action_number=events).join(truth, on="action_number")
    assert j.height == shots.height
    assert set((j["shot_distance"] - j["SHOT_DISTANCE"]).to_list()) <= {0, 1}
    corner = j.filter(pl.col("SHOT_ZONE_BASIC").str.contains("Corner 3"))
    assert corner.height >= 22 and corner["shot_distance"].min() >= 22


def test_shots_three_without_a_location_reads_null_not_zero() -> None:
    """1996-97 captures carry some threes at legacy (0, 0) -- no location at all.
    A three cannot be 0 ft, so those read null; located 22-ft threes (the
    shortened 1994-97 line) are restored like the modern corner."""
    pl = build.pl
    raw = build.build_pbp(SHOTS_FIX, 1997, ["0029600360"])
    shots = build.build_shots(raw)
    origin = shots.filter(pl.col("x_legacy") == 0, pl.col("y_legacy") == 0)
    assert origin.height == 4 and origin["shot_distance"].null_count() == 4
    located = shots.filter((pl.col("x_legacy") != 0) | (pl.col("y_legacy") != 0))
    assert located["shot_distance"].null_count() == 0
    assert located["shot_distance"].min() == 22
