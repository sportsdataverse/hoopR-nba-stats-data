"""``python -m nba_data_build.synergy_cli`` -- compile ``nba_stats_synergy`` from the raw store.

Synergy play types were swept into ``hoopR-nba-stats-raw`` long ago and never
compiled: 22 season directories, 1,096 payloads, and no release tag. This builds
them the same way ``leaguedash_cli`` builds its cube -- many tables into ONE tag,
one asset per ``(variant, season)``.

Unlike leaguedash this makes **no network calls**: every payload is already on
disk, so a compile is reproducible from a checkout.

Layout read::

    {raw}/synergyplaytypes/{season}/{season_type}_{play_type}_{grouping}_{per_mode}.json

88 variants = season_type x play_type x {offensive,defensive} x {pergame,totals}.
Each file is the standard stats.nba.com envelope with a single ``SynergyPlayType``
result set (24 headers, one row per player).

Example::

    python -m nba_data_build.synergy_cli --seasons 2024 2025
    python -m nba_data_build.synergy_cli --seasons 2024 --publish
"""

from __future__ import annotations

import argparse
import logging
import os
import re
from pathlib import Path
from typing import Optional

import polars as pl

from .publish import upload_artifacts
from .raw_compile import clear_seasons, read_result_sets

logger = logging.getLogger(__name__)

_REPO = "sportsdataverse/sportsdataverse-data"
_TAG = "nba_stats_synergy"
_ENDPOINT = "synergyplaytypes"

#: Seasons whose payloads actually carry rows. The raw store has directories back
#: to 1996 and forward to the current season, but synergy tracking only exists
#: from 2015 and the in-progress season is empty until games are played --
#: measured 2026-09-02: 1996-2005 and 2026 hold files with ZERO rows.
#: Publishing those would recreate exactly the schema-only-asset problem that put
#: 84 empty ``ncaa_baseball`` assets on a release (ledger L54). The empty-frame
#: skip in :func:`build` is the real guard; this is the default season list.
FIRST_SEASON = 2015
LAST_SEASON = 2025

#: ``{season_type}_{play_type}_{grouping}_{per_mode}`` -- play_type may itself
#: contain no underscores, so anchor on the known head and tail instead.
_STEM = re.compile(
    r"^(?P<season_type>regular-season|playoffs)_(?P<play_type>.+)_"
    r"(?P<grouping>offensive|defensive)_(?P<per_mode>pergame|totals)$"
)


def raw_root() -> Path:
    """The shared raw store, overridable for tests and sibling checkouts."""
    env = os.environ.get("HOOPR_NBA_STATS_RAW_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "hoopR-nba-stats-raw" / "nba_stats" / "json"


def read_variant(path: Path) -> pl.DataFrame:
    """One payload -> a tidy frame, or an EMPTY frame when it carries no rows.

    Thin alias kept for readability at the call site; the implementation is shared
    with the matchups and combine compilers in :mod:`raw_compile`.
    """
    return read_result_sets(path)


def _norm(value: object) -> str:
    """Compare labels ignoring case and separators: ``PRBallHandler`` == ``prballhandler``."""
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def _stamp(frame: pl.DataFrame, season: int, stem: str) -> pl.DataFrame:
    """Add the columns the filename carries that the payload does not.

    ``play_type`` and ``type_grouping`` ARE in the payload, so they are asserted
    against the filename rather than copied from it -- if the two ever disagree
    the capture is mislabelled and a silent overwrite would bake that in.
    """
    m = _STEM.match(stem)
    if m is None:
        raise ValueError(f"unparseable synergy stem: {stem!r}")
    # BOTH labels, not just the grouping: a payload named ..._cut_... that actually
    # holds Isolation rows would otherwise be written and published AS the cut
    # asset, silently corrupting that variant's statistics.
    for column, expected in (("type_grouping", m["grouping"]), ("play_type", m["play_type"])):
        if not frame.height or column not in frame.columns:
            continue
        seen = {_norm(v) for v in frame[column].unique().to_list()}
        if seen and seen != {_norm(expected)}:
            raise ValueError(
                f"{stem}: filename says {column}={expected!r} but payload says "
                f"{sorted(seen)} -- capture is mislabelled"
            )
    return frame.with_columns(
        season=pl.lit(season, dtype=pl.Int64),
        season_type=pl.lit(m["season_type"]),
        per_mode=pl.lit(m["per_mode"]),
    )


def build(seasons: list[int], out: Path, *, raw: Optional[Path] = None) -> dict[str, int]:
    """Compile every variant for ``seasons`` into ``out/nba_stats_synergy/``.

    Returns ``{"nba_stats_synergy/<variant>": rows}``. A season whose payloads are
    all empty writes NOTHING -- no zero-row asset is ever created.
    """
    raw = raw or raw_root()
    # once, before any endpoint: a tag can carry several endpoints and clearing
    # per endpoint would delete the previous one's freshly written assets
    clear_seasons(out, _TAG, seasons)
    written: dict[str, int] = {}
    for season in seasons:
        season_dir = raw / _ENDPOINT / str(season)
        if not season_dir.is_dir():
            logger.warning("synergy_missing_season season=%s dir=%s", season, season_dir)
            continue
        for path in sorted(season_dir.glob("*.json")):
            frame = read_variant(path)
            if not frame.height:
                logger.info("synergy_empty variant=%s season=%s", path.stem, season)
                continue
            frame = _stamp(frame, season, path.stem)
            dest = out / _TAG / f"{path.stem}_{season}.parquet"
            dest.parent.mkdir(parents=True, exist_ok=True)
            frame.write_parquet(dest)
            key = f"{_TAG}/{path.stem}"
            written[key] = written.get(key, 0) + frame.height
            logger.info(
                "synergy_write variant=%s season=%s rows=%s", path.stem, season, frame.height
            )
    return written


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nba_data_build.synergy_cli")
    p.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        default=list(range(FIRST_SEASON, LAST_SEASON + 1)),
        help=f"seasons to compile (default {FIRST_SEASON}-{LAST_SEASON}, the ones with rows)",
    )
    p.add_argument("--out", default="out", help="release staging dir")
    p.add_argument("--raw-root", default=None, help="override the raw store location")
    p.add_argument("--repo", default=_REPO)
    p.add_argument("--publish", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parser().parse_args(argv)
    out = Path(args.out)
    written = build(args.seasons, out, raw=Path(args.raw_root) if args.raw_root else None)
    for key, rows in sorted(written.items()):
        print(f"{key}: {rows} rows")
    if not written:
        print("nothing built -- no season produced rows; not publishing")
        return 0
    if (args.publish or args.dry_run) and (out / _TAG).exists():
        result = upload_artifacts(
            out / _TAG, _TAG, args.repo, seasons=args.seasons, dry_run=args.dry_run
        )
        if result["failed"]:
            print(f"WARNING: {len(result['failed'])} file(s) failed to publish: {result['failed']}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
