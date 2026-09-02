"""``hustle_cli`` compiles the two season-level hustle endpoints into one tag.

The layout is the matchups layout, so most of the behaviour is already pinned by
``test_raw_compile.py`` through the shared ``raw_compile`` helpers. What is
specific to this family and asserted here: the two endpoints land under one tag
without colliding, the floor is the MEASURED one, the ids stay Int64 join keys,
and the partial first season is treated as data rather than as an empty season.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import polars as pl
import pytest
from nba_data_build import hustle_cli, raw_compile

_PLAYER_HEADERS = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "DEFLECTIONS"]
_TEAM_HEADERS = ["TEAM_ID", "TEAM_NAME", "DEFLECTIONS"]
_TAG = "nba_stats_hustle"


def _season_file(
    raw: Path, endpoint: str, season: int, stem: str, headers: list[str], rows: list[list[object]]
) -> None:
    d = raw / endpoint / str(season)
    d.mkdir(parents=True, exist_ok=True)
    payload = {"resultSets": [{"name": "HustleStats", "headers": headers, "rowSet": rows}]}
    (d / f"{stem}.json").write_text(json.dumps(payload), encoding="utf-8")


def _both(raw: Path, season: int, stem: str) -> None:
    _season_file(
        raw,
        "leaguehustlestatsplayer",
        season,
        stem,
        _PLAYER_HEADERS,
        [[201166, "Aaron Brooks", 1610612750, 21]],
    )
    _season_file(
        raw,
        "leaguehustlestatsteam",
        season,
        stem,
        _TEAM_HEADERS,
        [[1610612737, "Atlanta Hawks", 812]],
    )


def test_the_two_endpoints_share_a_tag_without_colliding(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    _both(raw, 2024, "regular-season_totals")

    written = hustle_cli.build([2024], out, raw=raw)

    assert set(written) == {
        f"{_TAG}/leaguehustlestatsplayer_regular-season_totals",
        f"{_TAG}/leaguehustlestatsteam_regular-season_totals",
    }
    assert sorted(p.name for p in (out / _TAG).glob("*.parquet")) == [
        "leaguehustlestatsplayer_regular-season_totals_2024.parquet",
        "leaguehustlestatsteam_regular-season_totals_2024.parquet",
    ]


def test_ids_stay_int64_join_keys(tmp_path: Path) -> None:
    """Player and team ids arrive as JSON ints and must not drift to Utf8/Float.

    A float-origin id stringifies as ``"1610612750.0"``, which joins to nothing
    while looking perfectly well-formed -- so the dtype is asserted, not assumed.
    """
    raw, out = tmp_path / "raw", tmp_path / "out"
    _both(raw, 2024, "regular-season_totals")
    hustle_cli.build([2024], out, raw=raw)

    players = pl.read_parquet(
        out / _TAG / "leaguehustlestatsplayer_regular-season_totals_2024.parquet"
    )
    teams = pl.read_parquet(out / _TAG / "leaguehustlestatsteam_regular-season_totals_2024.parquet")
    assert players.schema["player_id"] == pl.Int64
    assert players.schema["team_id"] == pl.Int64
    assert teams.schema["team_id"] == pl.Int64
    # The two frames join on team_id, so their dtypes must agree on both sides.
    assert players.schema["team_id"] == teams.schema["team_id"]


def test_an_empty_season_ships_no_asset(tmp_path: Path) -> None:
    """2013-14 and 2014-15 answer a valid envelope with no rows; those are skipped."""
    raw, out = tmp_path / "raw", tmp_path / "out"
    _season_file(raw, "leaguehustlestatsplayer", 2014, "regular-season_totals", _PLAYER_HEADERS, [])
    _both(raw, 2015, "regular-season_totals")

    written = hustle_cli.build([2014, 2015], out, raw=raw)

    assert not list((out / _TAG).glob("*_2014.parquet"))
    assert all(rows > 0 for rows in written.values())


def test_the_floor_is_the_measured_one() -> None:
    """2015, from a live probe of the endpoint -- not from where capture happens to start.

    Lowering it would ship 2013-14/2014-15 as schema-only assets, which is how a
    tag comes to advertise coverage it does not have.
    """
    seasons = hustle_cli._parser().parse_args([]).seasons
    assert seasons[0] == 2015 and seasons[-1] == 2025
    assert 2026 not in seasons  # the in-progress season is still filling


def test_a_stem_the_layout_does_not_produce_raises(tmp_path: Path) -> None:
    """The filename is the only record of which slice a payload is."""
    raw, out = tmp_path / "raw", tmp_path / "out"
    _season_file(
        raw, "leaguehustlestatsplayer", 2024, "preseason_totals", _PLAYER_HEADERS, [[1, "x", 2, 3]]
    )
    with pytest.raises(ValueError, match="unparseable"):
        hustle_cli.build([2024], out, raw=raw)


def test_the_2015_regular_season_is_dropped_and_its_playoffs_kept(tmp_path: Path) -> None:
    """2015-16 regular season is 2 games; its playoffs are complete.

    Both halves are populated, so only the season-type-scoped skip separates
    them -- the empty-payload guard sees two non-empty frames.
    """
    raw, out = tmp_path / "raw", tmp_path / "out"
    _both(raw, 2015, "regular-season_totals")
    _both(raw, 2015, "playoffs_totals")

    written = hustle_cli.build([2015], out, raw=raw)

    names = sorted(p.name for p in (out / _TAG).glob("*.parquet"))
    assert names == [
        "leaguehustlestatsplayer_playoffs_totals_2015.parquet",
        "leaguehustlestatsteam_playoffs_totals_2015.parquet",
    ]
    assert not any("regular-season" in k for k in written)


def test_the_thin_skip_applies_to_2015_only(tmp_path: Path) -> None:
    """A blanket regular-season skip would empty the whole tag."""
    raw, out = tmp_path / "raw", tmp_path / "out"
    _both(raw, 2016, "regular-season_totals")

    hustle_cli.build([2016], out, raw=raw)

    assert (out / _TAG / "leaguehustlestatsplayer_regular-season_totals_2016.parquet").exists()
    assert not hustle_cli._thin(2016, "regular-season_totals")
    assert hustle_cli._thin(2015, "regular-season_pergame")
    assert not hustle_cli._thin(2015, "playoffs_totals")


def test_matchups_and_hustle_stamp_through_the_same_helper() -> None:
    """One grammar, one implementation -- a second copy would not fail, it would mis-stamp."""
    from nba_data_build import matchups_cli

    assert matchups_cli.stamp_season_type_per_mode is raw_compile.stamp_season_type_per_mode


# --------------------------------------------------------------------- real store


@pytest.mark.archive
def test_player_rows_sum_to_the_team_rows(tmp_path: Path) -> None:
    """The two endpoints are the same measurements at two grains, so they must agree.

    This is the gate a synthetic fixture cannot give: it is simultaneously a
    check on the capture (both endpoints, every season and season type, same
    slice), on the parse (no dropped or duplicated rows), and on the id handling
    (a player attached to the wrong team would still sum right league-wide, but a
    dropped frame would not). Measured exact -- not within a tolerance -- across
    every published season on 2026-09-02.
    """
    raw = Path(
        os.environ.get(
            "SDV_PY_NBA_RAW_JSON_DIR",
            Path(__file__).resolve().parents[2] / "hoopR-nba-stats-raw" / "nba_stats" / "json",
        )
    )
    if not (raw / "leaguehustlestatsplayer").is_dir():
        pytest.skip(f"no hustle capture under {raw}")

    seasons = list(range(hustle_cli.FIRST_SEASON, hustle_cli.LAST_SEASON + 1))
    out = tmp_path / "out"
    hustle_cli.build(seasons, out, raw=raw)

    measures = ("deflections", "contested_shots", "screen_assists", "charges_drawn", "box_outs")
    checked = 0
    for players in sorted((out / _TAG).glob("leaguehustlestatsplayer_*_totals_*.parquet")):
        teams = players.with_name(players.name.replace("player_", "team_", 1))
        assert teams.exists(), f"{players.name} has no team counterpart"
        p, t = pl.read_parquet(players), pl.read_parquet(teams)
        for col in measures:
            if col in t.columns:
                assert p[col].sum() == t[col].sum(), f"{players.name}: {col}"
        assert p.schema["team_id"] == t.schema["team_id"] == pl.Int64
        assert p["player_id"].null_count() == 0 and t["team_id"].null_count() == 0
        checked += 1
    assert checked >= 11, f"only {checked} season/type slices checked"
