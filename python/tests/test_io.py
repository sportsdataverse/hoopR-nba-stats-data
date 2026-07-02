from pathlib import Path
import polars as pl
from nba_data_build.io import write_possessions, write_rapm, write_report


def test_write_and_read_parquet(tmp_path):
    df = pl.DataFrame({"player_id": [1], "o_rapm": [0.5], "season": [2023]})
    p = tmp_path / "rapm" / "nba_rapm_2023.parquet"
    write_rapm(df, p)
    assert p.exists() and pl.read_parquet(p).equals(df)


def test_write_report_creates_dirs(tmp_path):
    p = tmp_path / "docs" / "card.md"
    write_report("# hi\n", p)
    assert p.read_text(encoding="utf-8") == "# hi\n"
