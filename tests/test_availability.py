import polars as pl
from nba_data_build.process.availability import compute_flags
from nba_data_build.scrape.raw_store import write_raw


def test_flags_reflect_disk(tmp_path):
    write_raw(tmp_path, "pbpv3", "0022300001", {})
    write_raw(tmp_path, "boxv3", "0022300001", {})
    # boxv3_periods intentionally absent
    sched = pl.DataFrame({"game_id": ["0022300001", "0022300099"], "PBP": [True, False]})
    out = compute_flags(tmp_path, sched)
    row = out.filter(pl.col("game_id") == "0022300001").to_dicts()[0]
    assert row["PBP_V3"] is True and row["BOX_V3"] is True and row["BOX_PERIODS"] is False
    absent = out.filter(pl.col("game_id") == "0022300099").to_dicts()[0]
    assert absent["PBP_V3"] is False
    # existing PBP flag untouched; new flags are Boolean
    for c in ["PBP_V3", "BOX_V3", "BOX_PERIODS", "POSS", "LINEUP"]:
        assert out.schema[c] == pl.Boolean


def _write_dataset_parquet(tmp_path, dataset_dir, game_ids):
    d = tmp_path / "nba_stats" / dataset_dir / "parquet"
    d.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"game_id": game_ids}).write_parquet(d / "seed.parquet")


def test_poss_lineup_true_when_present_on_disk(tmp_path):
    """Positive-branch: a game_id actually present in the possessions/lineups parquet -> True."""
    _write_dataset_parquet(tmp_path, "possessions", ["0022300001"])
    _write_dataset_parquet(tmp_path, "lineups", ["0022300001"])
    sched = pl.DataFrame({"game_id": ["0022300001", "0022300099"]})
    out = compute_flags(tmp_path, sched)
    row = out.filter(pl.col("game_id") == "0022300001").to_dicts()[0]
    assert row["POSS"] is True and row["LINEUP"] is True
    absent = out.filter(pl.col("game_id") == "0022300099").to_dicts()[0]
    assert absent["POSS"] is False and absent["LINEUP"] is False


def test_poss_lineup_injected_ids_skip_disk_scan(tmp_path):
    """Explicit possession_game_ids=/lineup_game_ids= short-circuit the disk scan entirely."""
    # no possessions/ or lineups/ directory on disk at all
    sched = pl.DataFrame({"game_id": ["0022300001", "0022300099"]})
    out = compute_flags(
        tmp_path,
        sched,
        possession_game_ids=["0022300001"],
        lineup_game_ids=["0022300001"],
    )
    row = out.filter(pl.col("game_id") == "0022300001").to_dicts()[0]
    assert row["POSS"] is True and row["LINEUP"] is True
    absent = out.filter(pl.col("game_id") == "0022300099").to_dicts()[0]
    assert absent["POSS"] is False and absent["LINEUP"] is False


def test_corrupt_parquet_does_not_crash_flags(tmp_path, caplog):
    """A truncated/garbage parquet file in a dataset dir must not blow up compute_flags."""
    good_dir = tmp_path / "nba_stats" / "possessions" / "parquet"
    good_dir.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"game_id": ["0022300001"]}).write_parquet(good_dir / "good.parquet")
    (good_dir / "corrupt.parquet").write_bytes(b"not a real parquet file, just garbage bytes")

    sched = pl.DataFrame({"game_id": ["0022300001", "0022300099"]})
    out = compute_flags(tmp_path, sched)  # must not raise
    row = out.filter(pl.col("game_id") == "0022300001").to_dicts()[0]
    assert row["POSS"] is True  # the good file's membership still counts
    absent = out.filter(pl.col("game_id") == "0022300099").to_dicts()[0]
    assert absent["POSS"] is False
