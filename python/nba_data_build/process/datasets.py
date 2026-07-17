"""Per-season v3 parquet rollups + resumable per-game cache.

Consumes :func:`~nba_data_build.process.from_raw.process_game`'s per-game
``ProcessedGame`` (enriched pbp / possessions / lineups, PIPELINE_VERSION>=3
possession semantics) and concatenates a season's worth of games into the
three committed datasets Task 10's build/publish flow drives:

- ``{root}/nba_stats/pbpv3/parquet/play_by_play_v3_{season}.parquet``
- ``{root}/nba_stats/possessions/parquet/nba_possessions_v3_{season}.parquet``
- ``{root}/nba_stats/lineups/parquet/nba_lineups_v3_{season}.parquet``

Resumability: :func:`write_game_cache` persists each game's three frames
under ``{cache_root}/games_{season}/`` (verbatim parquet, **not committed** --
a local scratch cache only) so re-running :func:`rollup_season` for a season
already in progress skips re-processing any game whose cache is present.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Union

import polars as pl

from ..cache_guard import assert_pipeline_version
from .from_raw import ProcessedGame, process_game

_FRAME_NAMES = ("enriched_pbp", "possessions", "lineups")


def _ensure_parent(path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _game_cache_dir(cache_root: Union[str, Path], season: int) -> Path:
    return Path(cache_root) / f"games_{season}"


def _game_cache_paths(cache_root: Union[str, Path], season: int, game_id: str) -> dict[str, Path]:
    """Per-frame cache paths for one game within a season's cache dir."""
    d = _game_cache_dir(cache_root, season)
    return {name: d / f"{game_id}_{name}.parquet" for name in _FRAME_NAMES}


def write_game_cache(cache_root: Union[str, Path], season: int, pg: ProcessedGame) -> None:
    """Persist one game's compiled frames to the resumability cache.

    Writes ``{cache_root}/games_{season}/{game_id}_{enriched_pbp,possessions,
    lineups}.parquet``. This cache is a local scratch artifact (never
    committed) -- :func:`rollup_season` reads it back to skip reprocessing a
    game already compiled in a prior run.

    Args:
        cache_root: Root directory for the per-game resumability cache.
        season: Season end-year (e.g. 2024 for 2023-24), used to
            namespace the cache directory per season.
        pg: The game's compiled :class:`~nba_data_build.process.from_raw.ProcessedGame`.

    Returns:
        None.

    Example:
        Quick start::

            from nba_data_build.process.datasets import write_game_cache
            from nba_data_build.process.from_raw import process_game
            pg = process_game("tests/fixtures/raw", "0022300001")
            write_game_cache("cache", 2023, pg)
    """
    paths = _game_cache_paths(cache_root, season, pg.game_id)
    for name, path in paths.items():
        _ensure_parent(path)
        getattr(pg, name).write_parquet(path)


def _read_game_cache(cache_root: Union[str, Path], season: int, game_id: str) -> Union[ProcessedGame, None]:
    """Read one game's cached frames back, or None if the cache is incomplete/absent."""
    paths = _game_cache_paths(cache_root, season, game_id)
    if not all(p.exists() for p in paths.values()):
        return None
    return ProcessedGame(
        game_id=str(game_id),
        enriched_pbp=pl.read_parquet(paths["enriched_pbp"]),
        possessions=pl.read_parquet(paths["possessions"]),
        lineups=pl.read_parquet(paths["lineups"]),
    )


_PLAYER_SLOT_RE = re.compile(r"^(off|def|home|away)_player_\d+$")


def _coerce_id_dtypes(df: pl.DataFrame) -> pl.DataFrame:
    """Pin the join-key dtype discipline post-concat: ``game_id`` Utf8, id columns Int64.

    ``diagonal_relaxed`` can widen a column's dtype across frames with
    differing (but compatible) types when concatenating (e.g. an all-null
    slot column from a game missing that lineup source lands as ``Null``
    dtype) -- reassert the canonical dtypes before write so every consumer
    sees the same schema. Covers both ``*_id``-suffixed columns
    (``offense_team_id``, ``player_id``, ...) and the per-slot on-court
    columns (``off_player_1``, ``home_player_5``, ...), which are id columns
    without an ``_id`` suffix.
    """
    exprs = []
    for name, dtype in df.schema.items():
        if name == "game_id":
            exprs.append(pl.col(name).cast(pl.Utf8))
        elif (name.endswith("_id") or _PLAYER_SLOT_RE.match(name)) and dtype != pl.Utf8:
            exprs.append(pl.col(name).cast(pl.Int64))
    return df.with_columns(exprs) if exprs else df


def rollup_season(
    root: Union[str, Path],
    season: int,
    game_ids: list[str],
    *,
    cache_root: Union[str, Path],
) -> dict[str, Path]:
    """Compile a season's games into the three committed v3 parquet datasets.

    Processes each game in *game_ids* (reusing :func:`_read_game_cache` when
    present, else :func:`~nba_data_build.process.from_raw.process_game` +
    :func:`write_game_cache`), concatenates each of the three per-game frames
    across the season via ``pl.concat(..., how="diagonal_relaxed")``, pins
    the ``game_id``/``*_id`` join-key dtypes, and writes the season's
    committed parquet.

    Args:
        root: Dataset root -- also the raw-store root consumed by
            ``process_game`` (``{root}/nba_stats/json/...``).
        season: Season end-year (e.g. 2024 for 2023-24).
        game_ids: 10-digit NBA Stats game ids to include in the season.
        cache_root: Root directory for the per-game resumability cache (see
            :func:`write_game_cache`).

    Returns:
        A dict with keys ``"pbpv3"``, ``"possessions"``, ``"lineups"``
        mapping to the three written parquet paths.

    Raises:
        RuntimeError: If the installed sdv-py ``PIPELINE_VERSION`` is below
            the Phase-B minimum (see
            :func:`~nba_data_build.cache_guard.assert_pipeline_version`).
        FileNotFoundError: If any game's raw capture is missing on disk and
            not already in the game cache.

    Example:
        Quick start::

            from nba_data_build.process.datasets import rollup_season
            paths = rollup_season("data", 2023, ["0022300001"], cache_root="cache")
            print(paths["possessions"])
    """
    assert_pipeline_version()

    games: list[ProcessedGame] = []
    for game_id in game_ids:
        cached = _read_game_cache(cache_root, season, game_id)
        if cached is not None:
            games.append(cached)
            continue
        pg = process_game(root, game_id)
        write_game_cache(cache_root, season, pg)
        games.append(pg)

    root = Path(root)
    out_paths = {
        "pbpv3": root / "nba_stats" / "pbpv3" / "parquet" / f"play_by_play_v3_{season}.parquet",
        "possessions": root / "nba_stats" / "possessions" / "parquet" / f"nba_possessions_v3_{season}.parquet",
        "lineups": root / "nba_stats" / "lineups" / "parquet" / f"nba_lineups_v3_{season}.parquet",
    }
    frames = {
        "pbpv3": [g.enriched_pbp for g in games],
        "possessions": [g.possessions for g in games],
        "lineups": [g.lineups for g in games],
    }
    for key, path in out_paths.items():
        combined = _coerce_id_dtypes(pl.concat(frames[key], how="diagonal_relaxed"))
        _ensure_parent(path)
        combined.write_parquet(path)

    return out_paths
