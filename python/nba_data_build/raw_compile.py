"""Shared pieces for compiling a stats.nba.com family out of the committed raw store.

Three families now use this — synergy, season matchups, and the draft combine —
and they differ only in layout and in which columns the filename carries:

``{endpoint}/{season}/{variant}.json``
    Season directories with a variant stem (synergy, ``leagueseasonmatchups``,
    ``matchupsrollup``).

``{endpoint}/{year}.json``
    Flat, one file per draft class (the five ``draftcombine*`` endpoints).

Everything else is common: parse the one result set, skip an empty one, stamp the
columns the payload does not carry, and write a parquet named for the asset.

**The empty skip is the point.** The raw store holds well-formed payloads with an
empty ``rowSet`` for seasons a family does not cover — synergy before 2015,
matchups before 2017, the combine before 2000, and the in-progress season in all
of them. Writing those produces schema-only assets that make a tag advertise
coverage it does not have, which is exactly how 84 empty ``ncaa_baseball`` assets
reached a release and had to be deleted (ledger L54).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import polars as pl
from sportsdataverse.nba import parse_nba_stats_result_sets

logger = logging.getLogger(__name__)

REPO = "sportsdataverse/sportsdataverse-data"


def read_result_sets(path: Path) -> pl.DataFrame:
    """One payload -> a tidy frame, or an EMPTY frame when it carries no rows.

    Empty is a real answer, not an error: an uncovered season returns a
    well-formed envelope with an empty ``rowSet``. Unreadable is also non-fatal —
    one bad file must not sink a multi-season compile.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("raw_unreadable file=%s error=%s", path.name, str(exc)[:120])
        return pl.DataFrame()
    frame = parse_nba_stats_result_sets(payload)
    if isinstance(frame, dict):  # multi-set payload: take the first populated set
        frame = next((f for f in frame.values() if f.height), pl.DataFrame())
    return frame


def write_asset(out: Path, tag: str, name: str, frame: pl.DataFrame) -> Path:
    """Write ``out/<tag>/<name>.parquet``; callers must have checked ``frame.height``."""
    dest = out / tag / f"{name}.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(dest)
    return dest


def clear_seasons(out: Path, tag: str, seasons: list[int]) -> int:
    """Drop any existing ``*_<season>.parquet`` in the staging dir before rebuilding it.

    Publishing uploads whatever the staging directory holds for the requested
    seasons, so a file left by an EARLIER run would ride along -- including one
    whose payload is now empty or unreadable and was therefore skipped this time.
    That would defeat the empty-asset guard by the back door: the guard stops us
    WRITING a bad asset, not uploading a stale one. Clearing first makes "what this
    run produced" and "what is in the directory" the same set.
    """
    d = out / tag
    if not d.is_dir():
        return 0
    stale = [f for season in seasons for f in d.glob(f"*_{season}.parquet")]
    for f in stale:
        f.unlink()
    if stale:
        logger.info("raw_cleared tag=%s seasons=%s files=%s", tag, len(seasons), len(stale))
    return len(stale)


def compile_season_dirs(
    raw: Path,
    endpoint: str,
    seasons: list[int],
    out: Path,
    tag: str,
    *,
    stamp,
    prefix: str = "",
) -> dict[str, int]:
    """``{endpoint}/{season}/{variant}.json`` -> one asset per populated variant.

    ``stamp(frame, season, stem)`` adds the filename-derived columns and may raise
    to reject a mislabelled capture. ``prefix`` disambiguates asset names when one
    tag carries more than one endpoint.
    """
    written: dict[str, int] = {}
    for season in seasons:
        season_dir = raw / endpoint / str(season)
        if not season_dir.is_dir():
            logger.warning("raw_missing_season endpoint=%s season=%s", endpoint, season)
            continue
        for path in sorted(season_dir.glob("*.json")):
            frame = read_result_sets(path)
            if not frame.height:
                logger.info(
                    "raw_empty endpoint=%s season=%s variant=%s", endpoint, season, path.stem
                )
                continue
            name = f"{prefix}{path.stem}"
            write_asset(out, tag, f"{name}_{season}", stamp(frame, season, path.stem))
            key = f"{tag}/{name}"
            written[key] = written.get(key, 0) + frame.height
            logger.info("raw_write asset=%s season=%s rows=%s", name, season, frame.height)
    return written


def compile_flat_years(
    raw: Path,
    endpoint: str,
    years: list[int],
    out: Path,
    tag: str,
    *,
    stamp,
) -> dict[str, int]:
    """``{endpoint}/{year}.json`` -> one asset per populated year."""
    written: dict[str, int] = {}
    for year in years:
        path = raw / endpoint / f"{year}.json"
        if not path.is_file():
            logger.warning("raw_missing_year endpoint=%s year=%s", endpoint, year)
            continue
        frame = read_result_sets(path)
        if not frame.height:
            logger.info("raw_empty endpoint=%s year=%s", endpoint, year)
            continue
        write_asset(out, tag, f"{endpoint}_{year}", stamp(frame, year))
        key = f"{tag}/{endpoint}"
        written[key] = written.get(key, 0) + frame.height
        logger.info("raw_write asset=%s year=%s rows=%s", endpoint, year, frame.height)
    return written
