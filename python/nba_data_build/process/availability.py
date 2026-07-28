"""Schedule-master v3 availability flags.

Adds boolean columns to a schedule frame reflecting what's *actually on
disk*, not what a scrape/rollup run merely intended to produce:

- ``PBP_V3`` / ``BOX_V3`` / ``BOX_PERIODS`` -- per-kind raw-capture
  presence via :func:`~nba_data_build.scrape.raw_store.raw_path`
  (mirrors :func:`~nba_data_build.scrape.raw_store.has_raw`, but reported
  per-kind rather than collapsed to one all-three flag).
- ``POSS`` / ``LINEUP`` -- membership of ``game_id`` in the written
  per-season possession/lineup parquet
  (:func:`~nba_data_build.process.datasets.rollup_season` output). These
  scan disk by default; pass an explicit id set to skip the scan (e.g.
  when the caller already has the ids from an in-progress rollup).

The existing ``PBP`` column (and every other schedule column) is left
untouched -- this module only *adds* columns.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional, Union

import polars as pl

from ..scrape.raw_store import resolve_raw_path

logger = logging.getLogger(__name__)

# out_col -> raw_store kind
_RAW_FLAGS = (
    ("PBP_V3", "pbpv3"),
    ("BOX_V3", "boxv3"),
    ("BOX_PERIODS", "boxv3_periods"),
)


def _dataset_game_ids(root: Union[str, Path], dataset_dir: str) -> set[str]:
    """Collect the ``game_id`` membership across every per-season parquet in a dataset.

    Reads ``{root}/nba_stats/{dataset_dir}/parquet/*.parquet`` (the layout
    written by :func:`~nba_data_build.process.datasets.rollup_season`).
    Returns an empty set when the dataset directory doesn't exist yet
    (dataset not written -- every game reports False, not an error).

    Args:
        root: Dataset root (same root passed to ``rollup_season``).
        dataset_dir: ``"possessions"`` or ``"lineups"``.

    Returns:
        The set of ``game_id`` strings present across all parquet files
        found, or an empty set if none exist. A file that fails to read
        (partially written / corrupt parquet) is skipped with a logged
        warning rather than raising -- one bad file must not take down
        the whole flags computation.
    """
    parquet_dir = Path(root) / "nba_stats" / dataset_dir / "parquet"
    if not parquet_dir.exists():
        return set()
    game_ids: set[str] = set()
    for path in sorted(parquet_dir.glob("*.parquet")):
        try:
            game_ids.update(pl.read_parquet(path, columns=["game_id"])["game_id"].cast(pl.Utf8).to_list())
        except Exception:
            # Deliberately broad: a truncated/corrupt parquet file can surface as a polars
            # ComputeError, a pyarrow error, or an underlying Rust-panic-wrapped exception --
            # the failure mode isn't worth pinning to one type. Scoped to a single file inside
            # the loop (never swallows the whole computation) and always logged, never silent.
            logger.warning("availability: unreadable parquet %s -- treating as not-available", path)
    return game_ids


def compute_flags(
    root: Union[str, Path],
    schedule: pl.DataFrame,
    *,
    possession_game_ids: Optional[Iterable[str]] = None,
    lineup_game_ids: Optional[Iterable[str]] = None,
) -> pl.DataFrame:
    """Add v3 availability flags to a schedule frame, reflecting on-disk reality.

    Args:
        root: Raw-store / dataset root (see
            :func:`~nba_data_build.scrape.raw_store.raw_path` and
            :func:`~nba_data_build.process.datasets.rollup_season`).
        schedule: Schedule frame with a ``game_id`` column (and, typically,
            the existing ``PBP`` column -- left untouched).
        possession_game_ids: Explicit set of ``game_id``s already present
            in the possessions dataset. When omitted (the default), scans
            ``{root}/nba_stats/possessions/parquet/*.parquet`` -- pass this
            to skip the disk scan (e.g. a caller mid-rollup that already
            has the ids in memory).
        lineup_game_ids: Same as *possession_game_ids*, for the lineups
            dataset.

    Returns:
        *schedule* with five new ``pl.Boolean`` columns appended: ``PBP_V3``,
        ``BOX_V3``, ``BOX_PERIODS``, ``POSS``, ``LINEUP``. All other columns
        (including ``PBP``) are unchanged.

    Example:
        Quick start::

            from nba_data_build.process.availability import compute_flags
            out = compute_flags("data", schedule_df)
            out.filter(pl.col("PBP_V3") & ~pl.col("POSS"))  # v3 pbp captured, not yet rolled up

    See Also:
        * `hoopR`_ -- schedule-master availability columns follow the same
          per-source-flag convention as the R-side schedule builders.

    .. _hoopR: https://hoopR.sportsdataverse.org
    """
    poss_ids = set(possession_game_ids) if possession_game_ids is not None else _dataset_game_ids(root, "possessions")
    lineup_ids = set(lineup_game_ids) if lineup_game_ids is not None else _dataset_game_ids(root, "lineups")

    game_ids = schedule["game_id"].cast(pl.Utf8).to_list()

    new_cols = [
        pl.Series(
            out_col,
            # resolve_ rather than raw_path: a capture in either store layout counts
            # as present, or legacy captures would report missing after the migration.
            [resolve_raw_path(root, kind, gid) is not None for gid in game_ids],
            dtype=pl.Boolean,
        )
        for out_col, kind in _RAW_FLAGS
    ]
    new_cols.append(pl.Series("POSS", [gid in poss_ids for gid in game_ids], dtype=pl.Boolean))
    new_cols.append(pl.Series("LINEUP", [gid in lineup_ids for gid in game_ids], dtype=pl.Boolean))

    return schedule.with_columns(new_cols)
