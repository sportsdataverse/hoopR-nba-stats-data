"""Schedule master + the single ``games_in_data_repo`` manifest (spec D34/D36).

Two artifacts, one pass, derived from the same in-memory frame so they cannot
drift:

``nba_stats/nba_stats_schedule_master.parquet``
    Every game the schedule knows about — the denominator, including games
    with nothing built.

``nba_stats/nba_stats_games_in_data_repo.parquet``
    Only games present in at least one compilation — the numerator, and what
    consumers join against.

The per-season frames are parsed from the raw store's ``scheduleleaguev2/{E}.json``
(every game, preseason through NBA Cup, END-year keyed) and every ``in_*`` flag
is read off the COMMITTED tree: a game is in a dataset when its id is in
``nba_stats/{key}/parquet/{stem}_{E}.parquet``. The R-era per-season
``schedules/parquet/schedule_{E}`` family this used to union was retired
2026-09-30 (incomplete, span-string seasons, only the R twin wrote it).

Game ids are pinned ``Utf8``: NBA ids are zero-padded ("0022300001"), so an
int-typed source is restored via ``zfill(10)`` rather than a lossy str cast.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from sportsdataverse.nba.nba_stats_parsers import parse_nba_stats_result_sets

#: ``in_*`` flag -> (tree dir under ``nba_stats/``, parquet stem). Explicit, not
#: registry-derived: ``in_pbp`` reads the v3 ``nba_play_by_play`` family, which
#: the nightly v3 refresh publishes and the reshape registry does not carry.
FLAG_SOURCES: dict[str, tuple[str, str]] = {
    "in_pbp": ("pbp", "nba_play_by_play"),
    "in_game_rosters": ("game_rosters", "game_rosters"),
    "in_officials": ("officials", "officials"),
    "in_player_boxscores": ("player_boxscores", "player_boxscores"),
    "in_team_boxscores": ("team_boxscores", "team_boxscores"),
}


def flag_columns() -> tuple[str, ...]:
    """The ``in_*`` column set."""
    return tuple(FLAG_SOURCES)


def _utf8_game_id(expr: pl.Expr, dtype: pl.DataType) -> pl.Expr:
    if dtype == pl.Utf8:
        return expr
    # An int-origin id lost its "00" league prefix; zfill restores the
    # canonical 10-char form. Never cast through float.
    return expr.cast(pl.Int64).cast(pl.Utf8).str.zfill(10)


def _ensure_flags(schedule: pl.DataFrame) -> pl.DataFrame:
    """Every flag exists (Boolean): absence must be representable."""
    missing = [pl.lit(False).alias(c) for c in flag_columns() if c not in schedule.columns]
    out = schedule.with_columns(missing) if missing else schedule
    return out.with_columns([pl.col(c).cast(pl.Boolean) for c in flag_columns()])


def season_schedule(payload: Any, season: int) -> pl.DataFrame:
    """One season's schedule from a raw ``scheduleleaguev2`` payload, ``season`` = END year.

    The payload's own ``season`` is the feed's ``seasonYear`` string; it is
    overwritten with the END-year Int so the master agrees with every asset name.
    """
    frame = parse_nba_stats_result_sets(payload)
    if frame.is_empty():
        return frame
    return frame.with_columns(pl.lit(season, dtype=pl.Int64).alias("season"))


def stamp_from_tree(schedule: pl.DataFrame, base: str | Path, season: int) -> pl.DataFrame:
    """Set every ``in_*`` flag from the committed ``{base}/{key}/parquet/{stem}_{season}``.

    A missing file means nothing of that dataset is committed for the season,
    so the flag is False for every game — never left unset.
    """
    out = schedule
    for flag, (key, stem) in FLAG_SOURCES.items():
        path = Path(base) / key / "parquet" / f"{stem}_{season}.parquet"
        gids: list[str] = []
        if path.is_file():
            built = pl.read_parquet(path, columns=["game_id"])
            gids = (
                built.select(_utf8_game_id(pl.col("game_id"), built.schema["game_id"]))["game_id"]
                .unique()
                .to_list()
            )
        out = out.with_columns(
            _utf8_game_id(pl.col("game_id"), out.schema["game_id"]).is_in(gids).alias(flag)
        )
    return out


def build_master(season_frames: list[pl.DataFrame]) -> pl.DataFrame:
    """Union season schedules into one frame with a pinned column order.

    Ragged seasons reconcile via ``diagonal_relaxed``; every flag is
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
    # The feed's game_date is "MM/DD/YYYY ..." (min/max would sort January
    # first), so prefer the ISO game_date_est's date part when present.
    date = None
    if "game_date_est" in master.columns:
        date = pl.col("game_date_est").str.slice(0, 10)
    elif "game_date" in master.columns:
        date = pl.col("game_date")
    if date is not None:
        aggs += [date.min().alias("first_date"), date.max().alias("last_date")]
    aggs += [pl.col(f).mean().alias(f"pct_{f}") for f in flags]
    return master.group_by(keys, maintain_order=True).agg(aggs).sort(keys)
