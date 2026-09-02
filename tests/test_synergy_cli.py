"""``synergy_cli`` compiles the raw synergy sweep without ever shipping an empty asset.

The guard that matters here is the empty-season one. The raw store holds
directories for 1996-2005 and the in-progress season that contain well-formed
payloads with an EMPTY ``rowSet``; writing those would publish schema-only
parquet that makes the tag advertise coverage it does not have. That is not
hypothetical -- it is exactly how 84 empty ``ncaa_baseball`` assets reached a
release (ledger L54) and had to be deleted.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from nba_data_build import synergy_cli

_HEADERS = [
    "SEASON_ID",
    "PLAYER_ID",
    "PLAYER_NAME",
    "TEAM_ID",
    "PLAY_TYPE",
    "TYPE_GROUPING",
    "PERCENTILE",
]


def _payload(rows: list[list[object]]) -> dict:
    return {
        "resource": "synergyplaytypes",
        "parameters": {},
        "resultSets": [{"name": "SynergyPlayType", "headers": _HEADERS, "rowSet": rows}],
    }


def _write(raw: Path, season: int, stem: str, rows: list[list[object]]) -> None:
    d = raw / "synergyplaytypes" / str(season)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.json").write_text(json.dumps(_payload(rows)), encoding="utf-8")


def _row(grouping: str = "Offensive") -> list[object]:
    return ["22024", 201939, "Player One", 1610612744, "Cut", grouping, 0.81]


def test_builds_one_asset_per_populated_variant(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write(raw, 2024, "regular-season_cut_offensive_pergame", [_row()])
    _write(raw, 2024, "playoffs_cut_offensive_totals", [_row(), _row()])

    written = synergy_cli.build([2024], out, raw=raw)

    assert written == {
        "nba_stats_synergy/regular-season_cut_offensive_pergame": 1,
        "nba_stats_synergy/playoffs_cut_offensive_totals": 2,
    }
    assert sorted(p.name for p in (out / "nba_stats_synergy").glob("*.parquet")) == [
        "playoffs_cut_offensive_totals_2024.parquet",
        "regular-season_cut_offensive_pergame_2024.parquet",
    ]


def test_an_all_empty_season_writes_nothing(tmp_path: Path) -> None:
    """The L54 guard: files present, zero rows -> no asset, not a schema-only one."""
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write(raw, 2003, "regular-season_cut_offensive_pergame", [])
    _write(raw, 2003, "playoffs_cut_offensive_totals", [])

    written = synergy_cli.build([2003], out, raw=raw)

    assert written == {}
    assert not (out / "nba_stats_synergy").exists(), (
        "an empty season must not create the tag directory, let alone an asset"
    )


def test_a_mixed_season_keeps_only_the_populated_variants(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write(raw, 2024, "regular-season_cut_offensive_pergame", [_row()])
    _write(raw, 2024, "regular-season_cut_defensive_pergame", [])

    written = synergy_cli.build([2024], out, raw=raw)

    assert list(written) == ["nba_stats_synergy/regular-season_cut_offensive_pergame"]
    names = [p.name for p in (out / "nba_stats_synergy").glob("*.parquet")]
    assert names == ["regular-season_cut_offensive_pergame_2024.parquet"]


def test_the_filename_stamps_reach_the_frame(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write(raw, 2024, "playoffs_postup_defensive_totals", [_row("Defensive")])

    synergy_cli.build([2024], out, raw=raw)
    df = pl.read_parquet(
        out / "nba_stats_synergy" / "playoffs_postup_defensive_totals_2024.parquet"
    )

    assert df["season"].to_list() == [2024]
    assert df.schema["season"] == pl.Int64
    assert df["season_type"].to_list() == ["playoffs"]
    assert df["per_mode"].to_list() == ["totals"]
    # join keys stay integral -- a float- or str-typed id silently breaks joins
    assert df.schema["player_id"] == pl.Int64
    assert df.schema["team_id"] == pl.Int64


def test_a_mislabelled_capture_is_refused_not_silently_stamped(tmp_path: Path) -> None:
    """Filename says defensive, payload says offensive -> raise.

    Trusting either side alone would bake a mislabelled capture into a published
    asset, and the two disagreeing is the only signal that it happened.
    """
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write(raw, 2024, "regular-season_cut_defensive_pergame", [_row("Offensive")])

    with pytest.raises(ValueError, match="mislabelled"):
        synergy_cli.build([2024], out, raw=raw)


def test_a_missing_season_directory_is_skipped_not_fatal(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write(raw, 2024, "regular-season_cut_offensive_pergame", [_row()])

    written = synergy_cli.build([2024, 1999], out, raw=raw)

    assert list(written) == ["nba_stats_synergy/regular-season_cut_offensive_pergame"]


def test_unreadable_payload_is_skipped_not_fatal(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    d = raw / "synergyplaytypes" / "2024"
    d.mkdir(parents=True)
    (d / "regular-season_cut_offensive_pergame.json").write_text("{not json", encoding="utf-8")

    assert synergy_cli.build([2024], out, raw=raw) == {}


def test_default_seasons_exclude_the_empty_eras() -> None:
    """Measured 2026-09-02: 1996-2005 and 2026 hold files with zero rows."""
    seasons = synergy_cli._parser().parse_args([]).seasons
    assert seasons[0] == 2015 and seasons[-1] == 2025
    assert 2026 not in seasons and 2003 not in seasons


def test_main_refuses_to_publish_when_nothing_built(tmp_path: Path, capsys) -> None:
    raw = tmp_path / "raw"
    _write(raw, 2003, "regular-season_cut_offensive_pergame", [])

    rc = synergy_cli.main(
        ["--seasons", "2003", "--out", str(tmp_path / "out"), "--raw-root", str(raw), "--publish"]
    )

    assert rc == 0
    assert "not publishing" in capsys.readouterr().out
