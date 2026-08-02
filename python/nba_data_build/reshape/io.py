"""Dataset IO — write the three released formats for one table/season.

Every released dataset ships **parquet + rds + csv**:

* ``parquet`` — canonical cross-engine format, the parity bar.
* ``rds``     — what ``hoopR::load_nba_*()`` reads. Written natively via
  :func:`sportsdataverse._rds.write_rds`; no R round-trip.
* ``csv``     — plain text (never ``.csv.gz``).

All three are **release artifacts**: they ship to the ``nba_stats_*`` tags on
``sportsdataverse-data`` and are not committed to this repo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl
from sportsdataverse._rds import write_rds

# The R producers stamp `make_hoopR_data()` before saveRDS, so the rds carries the
# hoopR S3 chain -- mirror it exactly (same vector as hoopR-nba-data).
RDS_CLASS: tuple[str, ...] = (
    "hoopR_data",
    "tbl_df",
    "tbl",
    "data.table",
    "data.frame",
)


def write_release_formats(
    df: pl.DataFrame,
    dest_dir: Path,
    stem: str,
    nba_type: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Path]:
    """Write ``{dest_dir}/{stem}.{parquet,rds,csv}``; return the written paths.

    ``dest_dir`` is the per-tag release directory (flat, one dir per release
    tag), matching this repo's publish layout.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = dest_dir / f"{stem}.parquet"
    rds_path = dest_dir / f"{stem}.rds"
    csv_path = dest_dir / f"{stem}.csv"

    df.write_parquet(parquet_path)
    # The R producers stamp make_hoopR_data(type, timestamp) before saveRDS, and
    # print.hoopR_data renders both -- an rds without them prints a blank header.
    write_rds(
        df,
        rds_path,
        cls=RDS_CLASS,
        attributes={
            "hoopR_timestamp": timestamp or datetime.now(timezone.utc),
            "hoopR_type": nba_type or stem,
        },
    )
    df.write_csv(csv_path)
    return {"parquet": parquet_path, "rds": rds_path, "csv": csv_path}
