"""`matchups_cli` and `combine_cli` compile their families without shipping an empty asset.

Same guard as synergy, on the two other layouts: season directories with a
variant stem (matchups) and flat per-year files (combine). Both hold well-formed
payloads with an empty ``rowSet`` for years the family does not cover -- matchups
before 2017, the combine before 2000, and the in-progress season in both -- and
writing those is how a tag comes to advertise coverage it does not have.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
from nba_data_build import combine_cli, matchups_cli

_HEADERS = ["SEASON_ID", "OFF_PLAYER_ID", "DEF_PLAYER_ID", "MATCHUP_MIN"]
_COMBINE_HEADERS = ["SEASON", "PLAYER_ID", "PLAYER_NAME", "HEIGHT_WO_SHOES"]


def _payload(headers: list[str], rows: list[list[object]], name: str = "SeasonMatchups") -> dict:
    return {"resultSets": [{"name": name, "headers": headers, "rowSet": rows}]}


def _season_file(
    raw: Path, endpoint: str, season: int, stem: str, rows: list[list[object]]
) -> None:
    d = raw / endpoint / str(season)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.json").write_text(json.dumps(_payload(_HEADERS, rows)), encoding="utf-8")


def _year_file(raw: Path, endpoint: str, year: int, rows: list[list[object]]) -> None:
    d = raw / endpoint
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{year}.json").write_text(
        json.dumps(_payload(_COMBINE_HEADERS, rows, name="Results")), encoding="utf-8"
    )


# --------------------------------------------------------------------------- matchups


def test_matchups_prefixes_the_endpoint_so_the_two_never_collide(tmp_path: Path) -> None:
    """Both endpoints use the SAME stems, so an unprefixed name would overwrite."""
    raw, out = tmp_path / "raw", tmp_path / "out"
    row = ["22024", 201939, 2544, 4.2]
    _season_file(raw, "leagueseasonmatchups", 2024, "regular-season_totals", [row])
    _season_file(raw, "matchupsrollup", 2024, "regular-season_totals", [row, row])

    written = matchups_cli.build([2024], out, raw=raw)

    assert written == {
        "nba_stats_matchups/leagueseasonmatchups_regular-season_totals": 1,
        "nba_stats_matchups/matchupsrollup_regular-season_totals": 2,
    }
    assert sorted(p.name for p in (out / "nba_stats_matchups").glob("*.parquet")) == [
        "leagueseasonmatchups_regular-season_totals_2024.parquet",
        "matchupsrollup_regular-season_totals_2024.parquet",
    ]


def test_matchups_skips_an_empty_season(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    _season_file(raw, "leagueseasonmatchups", 2003, "regular-season_totals", [])

    assert matchups_cli.build([2003], out, raw=raw) == {}
    assert not (out / "nba_stats_matchups").exists()


def test_matchups_stamps_the_filename_columns(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    _season_file(raw, "matchupsrollup", 2024, "playoffs_pergame", [["22024", 1, 2, 3.0]])

    matchups_cli.build([2024], out, raw=raw)
    df = pl.read_parquet(
        out / "nba_stats_matchups" / "matchupsrollup_playoffs_pergame_2024.parquet"
    )

    assert df["season"].to_list() == [2024]
    assert df.schema["season"] == pl.Int64
    assert df["season_type"].to_list() == ["playoffs"]
    assert df["per_mode"].to_list() == ["pergame"]


def test_matchups_default_seasons_start_where_the_data_does() -> None:
    seasons = matchups_cli._parser().parse_args([]).seasons
    assert seasons[0] == 2017 and seasons[-1] == 2025
    assert 2026 not in seasons


# --------------------------------------------------------------------------- combine


def test_combine_builds_one_asset_per_endpoint_year(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    _year_file(raw, "draftcombinestats", 2024, [[2024, 1, "A", 78.5]])
    _year_file(raw, "draftcombineplayeranthro", 2024, [[2024, 1, "A", 78.5], [2024, 2, "B", 80.0]])

    written = combine_cli.build([2024], out, raw=raw)

    assert written == {
        "nba_stats_draft_combine/draftcombinestats": 1,
        "nba_stats_draft_combine/draftcombineplayeranthro": 2,
    }
    assert sorted(p.name for p in (out / "nba_stats_draft_combine").glob("*.parquet")) == [
        "draftcombineplayeranthro_2024.parquet",
        "draftcombinestats_2024.parquet",
    ]


def test_combine_skips_an_empty_year(tmp_path: Path) -> None:
    """1996-1999 are present but empty for four of the five endpoints."""
    raw, out = tmp_path / "raw", tmp_path / "out"
    _year_file(raw, "draftcombinedrillresults", 1997, [])

    assert combine_cli.build([1997], out, raw=raw) == {}
    assert not (out / "nba_stats_draft_combine").exists()


def test_combine_stamps_the_season(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    _year_file(raw, "draftcombinespotshooting", 2020, [[2020, 7, "C", 77.0]])

    combine_cli.build([2020], out, raw=raw)
    df = pl.read_parquet(out / "nba_stats_draft_combine" / "draftcombinespotshooting_2020.parquet")

    assert df["season"].to_list() == [2020]
    assert df.schema["season"] == pl.Int64


def test_combine_missing_year_file_is_skipped_not_fatal(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    _year_file(raw, "draftcombinestats", 2024, [[2024, 1, "A", 78.5]])

    written = combine_cli.build([2024, 1901], out, raw=raw)

    assert list(written) == ["nba_stats_draft_combine/draftcombinestats"]


def test_combine_default_years_start_where_the_data_does() -> None:
    years = combine_cli._parser().parse_args([]).years
    assert years[0] == 2000 and years[-1] == 2026


def test_both_clis_refuse_to_publish_when_nothing_built(tmp_path: Path, capsys) -> None:
    raw = tmp_path / "raw"
    _season_file(raw, "leagueseasonmatchups", 2003, "regular-season_totals", [])
    _year_file(raw, "draftcombinestats", 1997, [])

    assert (
        matchups_cli.main(
            ["--seasons", "2003", "--out", str(tmp_path / "a"), "--raw-root", str(raw), "--publish"]
        )
        == 0
    )
    assert "not publishing" in capsys.readouterr().out
    assert (
        combine_cli.main(
            ["--years", "1997", "--out", str(tmp_path / "b"), "--raw-root", str(raw), "--publish"]
        )
        == 0
    )
    assert "not publishing" in capsys.readouterr().out


# --------------------------------------------------------------- stale-asset guard


def test_a_stale_asset_is_cleared_so_publishing_cannot_ship_it(tmp_path: Path) -> None:
    """The empty guard stops us WRITING a bad asset, not uploading an old one.

    Publishing uploads whatever the staging dir holds for the requested seasons, so
    a file from an earlier run — including one whose payload is now empty and was
    skipped this time — would ride along and defeat the guard by the back door.
    """
    raw, out = tmp_path / "raw", tmp_path / "out"
    _season_file(raw, "leagueseasonmatchups", 2024, "regular-season_totals", [["22024", 1, 2, 3.0]])
    matchups_cli.build([2024], out, raw=raw)
    assert (out / "nba_stats_matchups" / "leagueseasonmatchups_regular-season_totals_2024.parquet").exists()

    # the capture is re-swept and now comes back empty
    _season_file(raw, "leagueseasonmatchups", 2024, "regular-season_totals", [])
    assert matchups_cli.build([2024], out, raw=raw) == {}
    assert not list((out / "nba_stats_matchups").glob("*.parquet")), (
        "the stale asset survived and would have been published"
    )


def test_clearing_happens_once_per_build_not_once_per_endpoint(tmp_path: Path) -> None:
    """A tag carries several endpoints; clearing per endpoint would delete the
    previous endpoint's freshly written assets, leaving only the last one."""
    raw, out = tmp_path / "raw", tmp_path / "out"
    row = ["22024", 201939, 2544, 4.2]
    _season_file(raw, "leagueseasonmatchups", 2024, "regular-season_totals", [row])
    _season_file(raw, "matchupsrollup", 2024, "regular-season_totals", [row])

    matchups_cli.build([2024], out, raw=raw)

    assert sorted(p.name for p in (out / "nba_stats_matchups").glob("*.parquet")) == [
        "leagueseasonmatchups_regular-season_totals_2024.parquet",
        "matchupsrollup_regular-season_totals_2024.parquet",
    ]


def test_combine_clearing_keeps_all_five_endpoints(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    for ep in ("draftcombinestats", "draftcombineplayeranthro", "draftcombinedrillresults"):
        _year_file(raw, ep, 2024, [[2024, 1, "A", 78.5]])

    combine_cli.build([2024], out, raw=raw)

    assert len(list((out / "nba_stats_draft_combine").glob("*.parquet"))) == 3


def test_clearing_leaves_other_seasons_alone(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    _season_file(raw, "matchupsrollup", 2023, "playoffs_totals", [["22023", 1, 2, 3.0]])
    _season_file(raw, "matchupsrollup", 2024, "playoffs_totals", [["22024", 1, 2, 3.0]])
    matchups_cli.build([2023, 2024], out, raw=raw)

    # rebuild only 2024; 2023's asset must survive
    matchups_cli.build([2024], out, raw=raw)

    assert sorted(p.name for p in (out / "nba_stats_matchups").glob("*.parquet")) == [
        "matchupsrollup_playoffs_totals_2023.parquet",
        "matchupsrollup_playoffs_totals_2024.parquet",
    ]
