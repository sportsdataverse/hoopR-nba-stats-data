"""Dataset IO — write the three released formats for one table/season.

Every released dataset ships **parquet + rds + csv**:

* ``parquet`` — canonical cross-engine format, the parity bar.
* ``rds``     — what ``hoopR::load_nba_*()`` reads. Written natively via
  :func:`sportsdataverse._rds.write_rds`; no R round-trip.
* ``csv``     — plain text (never ``.csv.gz``).

All three are **release artifacts**: they ship to the ``nba_stats_*`` tags on
``sportsdataverse-data`` and are not committed to this repo (D36 retired the
in-tree csv/rds copies on 2026-08-07).

That rule covers the RESHAPED datasets this module writes. It is not a
repo-wide ban: the ``nba_player_impact`` MODEL artifacts are committed under
``nba_stats/player_impact/`` by ``scripts/nightly_nba_impact.sh`` — a release
asset is overwritten in place and keeps no history, so a model's published
output would otherwise have no record of what it produced on a given night.
See CLAUDE.md and ``models/REGISTRY.md`` (decision 2026-09-02).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
from sportsdataverse._rds import write_rds

from nba_data_build.models import check_stem

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
    # D39: frame-level schema assertion at the single write chokepoint. Drift
    # is reported loudly but only blocks the write under the strict env toggle
    # -- a stats.com column addition must not silently strand a daily publish.
    problems = check_stem(stem, df)
    for problem in problems:
        print(f"::warning ::schema drift {stem}: {problem}")
    if problems and os.environ.get("NBA_DATA_SCHEMA_STRICT") == "1":
        raise ValueError(f"schema drift for {stem}: {problems}")

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
