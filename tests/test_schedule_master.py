"""Schedule master (D34): registry-derived in_* flags, manifest, coverage.

Offline, fixture-backed. The load-bearing invariant: the ``in_*`` column set
exactly mirrors the ``DATASETS`` registry's game-level keys — a dataset added
to the registry gets its flag with no edit here, and a hand-listed flag with
no registry entry cannot exist.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl
import pytest
from nba_data_build.master import (
    GAME_LEVEL,
    build_coverage,
    build_master,
    flag_columns,
    games_in_data_repo,
    stamp_from_built,
    stamp_from_raw,
)
from nba_data_build.reshape.datasets import DATASETS

GIDS = ["0022300001", "0022300002", "0042300101"]

YEARLY_COLUMNS = ("game_id", "season", "season_type_id", "game_date")


def _yearly(season: str, gids: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "game_id": gids,
            "season": [season] * len(gids),
            "season_type_id": ["2"] * (len(gids) - 1) + ["4"],
            "game_date": [dt.date(2023, 10, 24)] * len(gids),
        }
    )


def test_flag_columns_exactly_mirror_the_registry():
    assert flag_columns() == tuple(f"in_{d.key}" for d in DATASETS if d.level == "game")
    assert len(flag_columns()) > 0


def test_master_schema_is_yearly_schema_plus_registry_flags():
    master = build_master([_yearly("2023-24", GIDS), _yearly("2024-25", ["0022400001"])])
    assert set(master.columns) == set(YEARLY_COLUMNS) | set(flag_columns())
    assert master.columns == sorted(master.columns)  # pinned order
    assert master.schema["game_id"] == pl.Utf8
    for flag in flag_columns():
        assert master.schema[flag] == pl.Boolean


def test_stamp_from_built_reads_the_run_artifacts(tmp_path: Path):
    dataset = GAME_LEVEL[0]  # pbp
    built = tmp_path / dataset.release_tag
    built.mkdir(parents=True)
    pl.DataFrame({"game_id": GIDS[:2]}).write_parquet(built / f"{dataset.stem}_2024.parquet")

    stamped = stamp_from_built(_yearly("2023-24", GIDS), tmp_path, 2024)
    assert stamped[f"in_{dataset.key}"].to_list() == [True, True, False]
    # Datasets with no built file this run stay False, not absent.
    for other in GAME_LEVEL[1:]:
        assert stamped[f"in_{other.key}"].to_list() == [False, False, False]


def test_stamp_from_built_restores_int_origin_ids(tmp_path: Path):
    """An Int64 built game_id ("22300001") must still match "0022300001"."""
    dataset = GAME_LEVEL[0]
    built = tmp_path / dataset.release_tag
    built.mkdir(parents=True)
    pl.DataFrame({"game_id": [int(g) for g in GIDS[:1]]}).write_parquet(
        built / f"{dataset.stem}_2024.parquet"
    )
    stamped = stamp_from_built(_yearly("2023-24", GIDS), tmp_path, 2024)
    assert stamped[f"in_{dataset.key}"].to_list() == [True, False, False]


def test_stamp_from_raw_uses_the_dataset_source_endpoint():
    endpoint_gids = {d.endpoint: {GIDS[0]} for d in GAME_LEVEL if d.endpoint}
    stamped = stamp_from_raw(_yearly("2023-24", GIDS), endpoint_gids)
    for dataset in GAME_LEVEL:
        assert stamped[f"in_{dataset.key}"].to_list() == [True, False, False]


def test_manifest_keeps_only_games_with_a_flag():
    frame = _yearly("2023-24", GIDS).with_columns(
        pl.Series(flag_columns()[0], [True, False, False])
    )
    master = build_master([frame])
    manifest = games_in_data_repo(master)
    assert manifest["game_id"].to_list() == [GIDS[0]]
    assert manifest.columns == master.columns  # same schema, filtered rows


def test_coverage_grain_and_rates():
    frame = _yearly("2023-24", GIDS).with_columns(pl.Series(flag_columns()[0], [True, True, False]))
    coverage = build_coverage(build_master([frame]))
    assert coverage.height == 2  # (2023-24, "2") + (2023-24, "4")
    regular = coverage.filter(pl.col("season_type_id") == "2").to_dicts()[0]
    assert regular["n_games"] == 2
    assert regular[f"pct_{flag_columns()[0]}"] == 1.0
    assert str(regular["first_date"]) == "2023-10-24"


def test_build_master_requires_frames():
    with pytest.raises(ValueError, match="at least one season frame"):
        build_master([])
