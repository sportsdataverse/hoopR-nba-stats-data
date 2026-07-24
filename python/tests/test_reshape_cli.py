"""CLI dispatch tests. The routing table and the season_floor gate are the only
non-trivial logic here; the builders and IO are covered elsewhere, so these stub
them and assert the wiring."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from nba_data_build.reshape import cli
from nba_data_build.reshape.datasets import DATASETS


def test_resolve_datasets_defaults_to_all_in_registry_order() -> None:
    assert cli._resolve_datasets(None) == list(DATASETS)


def test_resolve_datasets_subset_keeps_registry_order_and_dedupes() -> None:
    # request out of order + a duplicate; expect registry order, once each.
    got = [d.key for d in cli._resolve_datasets(["shots", "standings", "shots"])]
    order = [d.key for d in DATASETS]
    assert got == sorted({"shots", "standings"}, key=order.index)


def test_resolve_datasets_rejects_unknown_key() -> None:
    with pytest.raises(SystemExit):
        cli._resolve_datasets(["not_a_dataset"])


def test_shots_derives_from_the_passed_pbp_frame_without_rebuilding(
    monkeypatch,
) -> None:
    """shots must reuse the caller's pbp frame, not trigger a second build_pbp."""
    calls = {"build_pbp": 0, "build_shots": 0}

    def fake_build_pbp(root, season):
        calls["build_pbp"] += 1
        return pl.DataFrame({"x": [1]})

    def fake_build_shots(pbp):
        calls["build_shots"] += 1
        assert pbp.equals(pl.DataFrame({"x": [1]}))
        return pl.DataFrame({"shot": [1]})

    monkeypatch.setattr(cli._build, "build_pbp", fake_build_pbp)
    monkeypatch.setattr(cli._build, "build_shots", fake_build_shots)

    shots = next(d for d in DATASETS if d.key == "shots")
    pbp_frame = pl.DataFrame({"x": [1]})
    out = cli.build_dataset("root", shots, 2013, _pbp=pbp_frame)

    assert out.equals(pl.DataFrame({"shot": [1]}))
    assert calls == {"build_pbp": 0, "build_shots": 1}, "reused pbp, no rebuild"


def test_boxscores_route_to_team_and_player_levels(monkeypatch) -> None:
    seen = []
    monkeypatch.setattr(
        cli._build,
        "build_boxscores",
        lambda root, season, *, team_level: seen.append(team_level) or pl.DataFrame(),
    )
    for key in ("player_boxscores", "team_boxscores"):
        ds = next(d for d in DATASETS if d.key == key)
        cli.build_dataset("root", ds, 2013)
    assert seen == [False, True]


def test_season_floor_skips_pre_floor_season_and_builds_at_the_floor(
    monkeypatch, tmp_path: Path
) -> None:
    """lineups (season_floor=2007) must be skipped for 2006 and built for 2007."""
    built_seasons: list[int] = []

    def fake_build(root, dataset, season):
        built_seasons.append(season)
        return pl.DataFrame({"x": [1]})

    # Keep the test off disk / off the rds writer: the gate is upstream of both.
    monkeypatch.setattr(cli._build, "build", fake_build)
    monkeypatch.setattr(
        cli,
        "write_release_formats",
        lambda *a, **k: {"parquet": Path("lineups_2007.parquet")},
    )

    rc = cli.main(
        [
            "--seasons",
            "2006",
            "2007",
            "--datasets",
            "lineups",
            "--out",
            str(tmp_path),
        ]
    )

    assert rc == 0
    assert built_seasons == [2007], "2006 gated by season_floor, 2007 built"
