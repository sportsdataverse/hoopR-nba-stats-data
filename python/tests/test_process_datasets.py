import shutil

import polars as pl

from nba_data_build.process.datasets import rollup_season


def test_rollup_writes_three_datasets(tmp_path):
    # raw fixture lives under tests/fixtures/raw; write outputs into tmp_path
    shutil.copytree("tests/fixtures/raw/nba_stats", tmp_path / "nba_stats")
    paths = rollup_season(tmp_path, 2023, ["0022300001"], cache_root=tmp_path / "cache")
    assert set(paths) == {"pbpv3", "possessions", "lineups"}
    poss = pl.read_parquet(paths["possessions"])
    assert poss.height > 0 and poss["game_id"].dtype == pl.Utf8
    # round-trip: re-run reuses the game cache (no reprocess needed) and is identical
    paths2 = rollup_season(tmp_path, 2023, ["0022300001"], cache_root=tmp_path / "cache")
    assert pl.read_parquet(paths2["possessions"]).equals(poss)
