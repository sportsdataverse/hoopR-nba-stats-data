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
