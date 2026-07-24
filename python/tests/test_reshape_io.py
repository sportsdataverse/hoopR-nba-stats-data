"""IO tests — the three release formats and the hoopR rds stamp.

``sportsdataverse._rds`` ships only a writer, so the rds is verified by gunzipping the
XDR stream and asserting the ``hoopR_data`` class chain and both stamped attribute keys
are embedded (their names are stored as literal CHARSXP strings in the serialized form).
"""

from __future__ import annotations

import gzip
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from nba_data_build.reshape.io import RDS_CLASS, write_release_formats


def _rds_xdr(path: Path) -> bytes:
    """Decompressed RDS bytes (saveRDS writes a gzip stream)."""
    return gzip.decompress(path.read_bytes())


def test_writes_all_three_formats(tmp_path: Path) -> None:
    df = pl.DataFrame({"season": [2013, 2013], "team_id": [1610612737, 1610612738]})
    paths = write_release_formats(
        df,
        tmp_path,
        "standings",
        nba_type="NBA Stats League Standings V3 from hoopR data repository",
        timestamp=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )
    assert set(paths) == {"parquet", "rds", "csv"}
    for p in paths.values():
        assert p.exists() and p.stat().st_size > 0
    # parquet round-trips to the same frame
    assert pl.read_parquet(paths["parquet"]).equals(df)


def test_rds_embeds_the_hoopR_class_chain(tmp_path: Path) -> None:
    df = pl.DataFrame({"season": [2013, 2013], "x": [1, 2]})
    paths = write_release_formats(df, tmp_path, "standings", nba_type="hoopR type")
    xdr = _rds_xdr(paths["rds"])
    for cls in RDS_CLASS:
        assert cls.encode() in xdr, f"class {cls!r} missing from rds"
    assert RDS_CLASS == (
        "hoopR_data",
        "tbl_df",
        "tbl",
        "data.table",
        "data.frame",
    )


def test_rds_embeds_both_stamp_attributes(tmp_path: Path) -> None:
    df = pl.DataFrame({"season": [2013, 2013], "x": [1, 2]})
    paths = write_release_formats(
        df,
        tmp_path,
        "standings",
        nba_type="NBA Stats Standings from hoopR data repository",
    )
    xdr = _rds_xdr(paths["rds"])
    assert b"hoopR_timestamp" in xdr
    assert b"hoopR_type" in xdr
    assert b"NBA Stats Standings from hoopR data repository" in xdr


def test_nba_type_defaults_to_stem(tmp_path: Path) -> None:
    df = pl.DataFrame({"season": [2013]})
    paths = write_release_formats(df, tmp_path, "officials")
    assert b"officials" in _rds_xdr(paths["rds"])
