"""Offline tests for the release-format derivation. No network, no R, no uploads."""

from __future__ import annotations

import datetime as dt
import gzip

import polars as pl
import pytest
from nba_data_build import v3_formats as vf


def _frame(rows=3):
    return pl.DataFrame(
        {
            # a zero-padded string id: the column most likely to be silently
            # corrupted into "123.0" by a format round trip
            "game_id": [f"002250000{i}" for i in range(rows)],
            "pts": list(range(rows)),
            "big_id": [9_000_000_000 + i for i in range(rows)],
            "pct": [0.5, None, 1.5][:rows],
            "made": [True, False, True][:rows],
            "game_date": [dt.date(2026, 1, 1 + i) for i in range(rows)],
        }
    )


def _staged(tmp_path, name="nba_play_by_play_2026"):
    p = tmp_path / f"{name}.parquet"
    df = _frame()
    df.write_parquet(p)
    return p, df


# --------------------------------------------------------------------------- derivation


def test_derive_writes_all_three_formats(tmp_path):
    p, _ = _staged(tmp_path)
    out = vf.derive_formats(p, tmp_path / "_release_build", dataset="pbp")
    assert set(out) == set(vf.FORMATS)
    assert out["parquet"] == p
    assert out["rds"].name == "nba_play_by_play_2026.rds"
    assert out["csv.gz"].name == "nba_play_by_play_2026.csv.gz"
    assert all(v.stat().st_size > 0 for v in out.values())


def test_csv_is_gzipped_and_decompresses_to_the_same_frame(tmp_path):
    """Existence alone would pass on a truncated file -- parse it back."""
    p, df = _staged(tmp_path)
    out = vf.derive_formats(p, tmp_path / "_release_build")
    raw = out["csv.gz"].read_bytes()
    assert raw[:2] == b"\x1f\x8b"  # gzip magic
    with gzip.open(out["csv.gz"], "rb") as fh:
        back = pl.read_csv(fh, schema_overrides={"game_id": pl.Utf8})
    assert back.shape == df.shape
    assert back.columns == df.columns
    assert back["game_id"].to_list() == df["game_id"].to_list()


def test_csv_gz_is_byte_deterministic(tmp_path):
    """No embedded mtime: a rebuild must not produce a 'changed' asset."""
    p, df = _staged(tmp_path)
    a = vf.write_csv_gz(df, tmp_path / "a.csv.gz").read_bytes()
    b = vf.write_csv_gz(df, tmp_path / "b.csv.gz").read_bytes()
    assert a == b


def test_derivation_is_reused_and_forceable(tmp_path):
    p, _ = _staged(tmp_path)
    out = tmp_path / "_release_build"
    first = vf.derive_formats(p, out)["rds"]
    stamp = first.stat().st_mtime_ns
    assert vf.derive_formats(p, out)["rds"].stat().st_mtime_ns == stamp  # reused
    assert vf.derive_formats(p, out, force=True)["rds"].stat().st_mtime_ns != stamp


# --------------------------------------------------------------------------- rds round trip


def test_rds_round_trips_shape_names_and_types(tmp_path):
    p, df = _staged(tmp_path)
    out = vf.derive_formats(p, tmp_path / "_release_build")
    got = vf.read_rds_structure(out["rds"])
    assert (got.nrows, got.ncols) == (df.height, df.width)
    assert got.names == df.columns
    assert got.types == ["character", "integer", "double", "double", "logical", "double"]


def test_rds_carries_the_hoopr_s3_class_chain(tmp_path):
    """hoopR registers S3 methods on `hoopR_data`; R only dispatches data.frame last."""
    p, _ = _staged(tmp_path)
    out = vf.derive_formats(p, tmp_path / "_release_build")
    got = vf.read_rds_structure(out["rds"])
    assert got.cls == list(vf.RDS_CLASS)
    assert got.cls[0] == "hoopR_data" and got.cls[-1] == "data.frame"


def test_verify_rds_rejects_a_shape_mismatch(tmp_path):
    p, df = _staged(tmp_path)
    out = vf.derive_formats(p, tmp_path / "_release_build")
    with pytest.raises(ValueError, match="rds is"):
        vf.verify_rds(out["rds"], df.head(1))


def test_verify_rds_rejects_a_renamed_column(tmp_path):
    p, df = _staged(tmp_path)
    out = vf.derive_formats(p, tmp_path / "_release_build")
    with pytest.raises(ValueError, match="column names differ"):
        vf.verify_rds(out["rds"], df.rename({"game_id": "gid"}))


def test_verify_rds_rejects_a_type_drift(tmp_path):
    """A Utf8 id read back as a double is the "123.0" corruption class."""
    p, df = _staged(tmp_path)
    out = vf.derive_formats(p, tmp_path / "_release_build")
    lied = df.with_columns(pl.col("game_id").str.len_chars().cast(pl.Float64))
    with pytest.raises(ValueError, match="in the rds") as excinfo:
        vf.verify_rds(out["rds"], lied)
    assert "game_id" in str(excinfo.value)


def test_reading_a_truncated_rds_raises_rather_than_reporting_a_short_frame(tmp_path):
    p, _ = _staged(tmp_path)
    out = vf.derive_formats(p, tmp_path / "_release_build")
    bad = tmp_path / "truncated.rds"
    bad.write_bytes(out["rds"].read_bytes()[: out["rds"].stat().st_size // 2])
    with pytest.raises((ValueError, EOFError)):
        vf.read_rds_structure(bad)


def test_a_failed_verification_does_not_leave_the_bad_rds_behind(tmp_path, monkeypatch):
    """A bad artifact left on disk would be reused as 'current' by the next run."""
    p, _ = _staged(tmp_path)
    out_dir = tmp_path / "_release_build"

    def boom(*_a, **_k):
        raise ValueError("simulated drift")

    monkeypatch.setattr(vf, "verify_rds", boom)
    with pytest.raises(ValueError, match="simulated drift"):
        vf.derive_formats(p, out_dir)
    assert not (out_dir / "nba_play_by_play_2026.rds").exists()
