"""CLI: decide seasons (explicit / incremental), build them, optionally publish."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from sportsdataverse.nba.nba_schedule import most_recent_nba_season

from .build import build
from .incremental import detect_missing_seasons
from .publish import published_seasons, upload_artifacts

_REPO = "sportsdataverse/sportsdataverse-data"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="nba_data_build")
    ap.add_argument("--seasons", type=int, nargs="+", default=None,
                    help="explicit season start-years (bypass incremental detection)")
    ap.add_argument("--latest-n", type=int, default=None,
                    help="force the last N seasons through --through (rebuild)")
    ap.add_argument("--through", type=int, default=None,
                    help="target through-season start-year (default: most_recent_nba_season())")
    ap.add_argument("--first", type=int, default=2021, help="earliest season for detection")
    ap.add_argument("--out", default="build_out", help="output directory")
    ap.add_argument("--cache-dir", default=None, help="compile cache dir")
    ap.add_argument("--repo", default=_REPO, help="release repo")
    ap.add_argument("--publish", action="store_true", help="upload artifacts to releases")
    ap.add_argument("--dry-run", action="store_true", help="plan publish without uploading")
    return ap


def _resolve_seasons(args: argparse.Namespace) -> list[int]:
    if args.seasons is not None:
        return sorted(args.seasons)
    through = args.through if args.through is not None else most_recent_nba_season()
    if args.latest_n is not None:
        return list(range(through - args.latest_n + 1, through + 1))
    return detect_missing_seasons(published_seasons("nba_stats_rapm", args.repo), through, args.first)


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    seasons = _resolve_seasons(args)
    out = Path(args.out)
    if not seasons:
        print("nothing to build (all seasons present)")
        return 0
    print(f"building seasons: {seasons}")
    build(seasons, out, cache_dir=args.cache_dir)
    if args.publish or args.dry_run:
        upload_artifacts(out / "rapm", "nba_stats_rapm", args.repo, dry_run=args.dry_run)
        upload_artifacts(out / "possessions", "nba_stats_possessions", args.repo, dry_run=args.dry_run)
    return 0
