"""``python -m nba_data_build.combine_cli`` -- compile ``nba_stats_draft_combine``.

Five captured-but-never-compiled endpoints, one file per draft class:

``draftcombinestats``          the headline measurement + drill table
``draftcombineplayeranthro``   height, wingspan, standing reach, body fat
``draftcombinedrillresults``   lane agility, shuttle, sprint, vertical
``draftcombinespotshooting``   spot-up makes/attempts by location
``draftcombinenonstationaryshooting``  on-the-move shooting

This is distinct from ``nba_stats_draft``, which is draft **history** (who was
picked where) and carries none of the measurements.

Layout is flat -- ``{endpoint}/{year}.json`` -- so there is no season directory
and no variant stem; the year is the only stamp.

Makes no network calls.

Example::

    python -m nba_data_build.combine_cli --years 2024 2025
    python -m nba_data_build.combine_cli --publish
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

import polars as pl

from .publish import upload_artifacts
from .raw_compile import REPO, clear_seasons, compile_flat_years
from .synergy_cli import raw_root

logger = logging.getLogger(__name__)

_TAG = "nba_stats_draft_combine"
_ENDPOINTS = (
    "draftcombinestats",
    "draftcombineplayeranthro",
    "draftcombinedrillresults",
    "draftcombinespotshooting",
    "draftcombinenonstationaryshooting",
)

#: Measured 2026-09-02: rows exist 2000-2026. The 1996-1999 files are present but
#: empty for four of the five endpoints, so the floor is the data's, not the
#: directory listing's.
FIRST_YEAR = 2000
LAST_YEAR = 2026


def _stamp(frame: pl.DataFrame, year: int) -> pl.DataFrame:
    return frame.with_columns(season=pl.lit(year, dtype=pl.Int64))


def build(years: list[int], out: Path, *, raw: Optional[Path] = None) -> dict[str, int]:
    """Compile all five combine endpoints into ``out/nba_stats_draft_combine/``."""
    raw = raw or raw_root()
    # once, before any endpoint: a tag can carry several endpoints and clearing
    # per endpoint would delete the previous one's freshly written assets
    clear_seasons(out, _TAG, years)
    written: dict[str, int] = {}
    for endpoint in _ENDPOINTS:
        written.update(compile_flat_years(raw, endpoint, years, out, _TAG, stamp=_stamp))
    return written


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nba_data_build.combine_cli")
    p.add_argument(
        "--years",
        type=int,
        nargs="+",
        default=list(range(FIRST_YEAR, LAST_YEAR + 1)),
        help=f"draft classes to compile (default {FIRST_YEAR}-{LAST_YEAR}, the ones with rows)",
    )
    p.add_argument("--out", default="out")
    p.add_argument("--raw-root", default=None)
    p.add_argument("--repo", default=REPO)
    p.add_argument("--publish", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parser().parse_args(argv)
    out = Path(args.out)
    written = build(args.years, out, raw=Path(args.raw_root) if args.raw_root else None)
    for key, rows in sorted(written.items()):
        print(f"{key}: {rows} rows")
    if not written:
        print("nothing built -- no year produced rows; not publishing")
        return 0
    if (args.publish or args.dry_run) and (out / _TAG).exists():
        result = upload_artifacts(
            out / _TAG, _TAG, args.repo, seasons=args.years, dry_run=args.dry_run
        )
        if result["failed"]:
            print(f"WARNING: {len(result['failed'])} file(s) failed to publish: {result['failed']}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
