"""Schedule master + the single ``games_in_data_repo`` manifest (spec D34/D36).

Two artifacts, one pass, derived from the same in-memory frame so they cannot
drift:

``nba_stats/nba_stats_schedule_master.parquet``
    Every game the schedule knows about — the denominator, including games
    with nothing built.

``nba_stats/nba_stats_games_in_data_repo.parquet``
    Only games present in at least one compilation — the numerator, and what
    consumers join against.

The committed per-season schedule files (``nba_stats/schedules/parquet``) are
the ORIGIN of every ``in_*`` flag; this module unions and normalizes but never
invents a flag. The flag SET is derived from the ``DATASETS`` registry
(``level == "game"``), never hand-listed, so a dataset added to the registry
gets its flag with no wiring here.

Game ids are pinned ``Utf8``: NBA ids are zero-padded ("0022300001"), so an
int-typed source is restored via ``zfill(10)`` rather than a lossy str cast.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import polars as pl

from nba_data_build.reshape.datasets import DATASETS, Dataset

#: Game-level datasets that roll up into a season release and so get a flag.
GAME_LEVEL: tuple[Dataset, ...] = tuple(d for d in DATASETS if d.level == "game")

#: Per-game raw files: "00" league prefix + 8 digits.
_GAME_FILE_RE = re.compile(r"^(00\d{8})\.json$")


def flag_columns() -> tuple[str, ...]:
    """The ``in_*`` column set, derived from the registry."""
    return tuple(f"in_{d.key}" for d in GAME_LEVEL)


def _utf8_game_id(expr: pl.Expr, dtype: pl.DataType) -> pl.Expr:
    if dtype == pl.Utf8:
        return expr
    # An int-origin id lost its "00" league prefix; zfill restores the
    # canonical 10-char form. Never cast through float.
    return expr.cast(pl.Int64).cast(pl.Utf8).str.zfill(10)


def _ensure_flags(schedule: pl.DataFrame) -> pl.DataFrame:
    """Every registry flag exists (Boolean): absence must be representable."""
    missing = [pl.lit(False).alias(c) for c in flag_columns() if c not in schedule.columns]
    out = schedule.with_columns(missing) if missing else schedule
    return out.with_columns([pl.col(c).cast(pl.Boolean) for c in flag_columns()])


def stamp_from_built(schedule: pl.DataFrame, built_dir: str | Path, season: int) -> pl.DataFrame:
    """Restamp ``in_*`` from this run's built season artifacts (the exact truth).

    ``built_dir`` follows the reshape CLI's output contract:
    ``{out}/{release_tag}/{stem}_{season}.parquet``. A dataset without a built
    file this run keeps whatever flag the season file already carries.
    """
    out = schedule
    for dataset in GAME_LEVEL:
        path = Path(built_dir) / dataset.release_tag / f"{dataset.stem}_{season}.parquet"
        if not path.is_file():
            continue
        built = pl.read_parquet(path, columns=["game_id"])
        gids = (
            built.select(_utf8_game_id(pl.col("game_id"), built.schema["game_id"]))["game_id"]
            .unique()
            .to_list()
        )
        out = out.with_columns(
            _utf8_game_id(pl.col("game_id"), out.schema["game_id"])
            .is_in(gids)
            .alias(f"in_{dataset.key}")
        )
    return _ensure_flags(out)


def raw_store_game_ids(raw_root: str | Path) -> dict[str, set[str]]:
    """Game-id sets per source endpoint of the game-level datasets, one scandir sweep."""
    sets: dict[str, set[str]] = {}
    for endpoint in {d.endpoint for d in GAME_LEVEL if d.endpoint}:
        gids: set[str] = set()
        base = Path(raw_root) / endpoint
        if base.is_dir():
            with os.scandir(base) as seasons:
                season_dirs = [e.path for e in seasons if e.is_dir()]
            for season_dir in season_dirs:
                with os.scandir(season_dir) as files:
                    for file in files:
                        match = _GAME_FILE_RE.match(file.name)
                        if match is not None:
                            gids.add(match.group(1))
        sets[endpoint] = gids
    return sets


def stamp_from_raw(schedule: pl.DataFrame, endpoint_gids: dict[str, set[str]]) -> pl.DataFrame:
    """Restamp ``in_*`` from raw-store presence of each dataset's source endpoint.

    ponytail: the reshaper is a pure function of the raw store, so raw presence
    is a faithful proxy for compilation membership — except that a captured
    ``boxscoresummaryv2`` can carry an empty result set. ``stamp_from_built``
    (exact, from the run's artifacts) wins whenever a build just happened.
    """
    out = schedule
    for dataset in GAME_LEVEL:
        gids = endpoint_gids.get(dataset.endpoint or "", set())
        out = out.with_columns(
            _utf8_game_id(pl.col("game_id"), out.schema["game_id"])
            .is_in(sorted(gids))
            .alias(f"in_{dataset.key}")
        )
    return _ensure_flags(out)


def build_master(season_frames: list[pl.DataFrame]) -> pl.DataFrame:
    """Union season schedules into one frame with a pinned column order.

    Ragged seasons reconcile via ``diagonal_relaxed``; every registry flag is
    materialized (False, not absent) so the master schema is stable.

    Raises:
        ValueError: If no frames are given.
    """
    if not season_frames:
        raise ValueError("build_master() requires at least one season frame")
    master = pl.concat([_ensure_flags(f) for f in season_frames], how="diagonal_relaxed")
    master = master.select(sorted(master.columns))
    keys = [k for k in ("season", "game_id") if k in master.columns]
    return master.sort(keys) if keys else master


def games_in_data_repo(master: pl.DataFrame) -> pl.DataFrame:
    """Only games present in at least one compilation."""
    flags = [c for c in master.columns if c.startswith("in_")]
    if not flags:
        return master.head(0)
    return master.filter(pl.any_horizontal([pl.col(c) == True for c in flags]))


def build_coverage(master: pl.DataFrame) -> pl.DataFrame:
    """One row per (season, season_type_id) with per-dataset build coverage."""
    flags = sorted(c for c in master.columns if c.startswith("in_"))
    keys = [k for k in ("season", "season_type", "season_type_id") if k in master.columns][:2]
    if not keys:
        raise ValueError("master frame has neither season nor a season_type column")
    aggs: list[pl.Expr] = [pl.len().alias("n_games")]
    if "game_date" in master.columns:
        aggs += [
            pl.col("game_date").min().alias("first_date"),
            pl.col("game_date").max().alias("last_date"),
        ]
    aggs += [pl.col(f).mean().alias(f"pct_{f}") for f in flags]
    return master.group_by(keys, maintain_order=True).agg(aggs).sort(keys)
