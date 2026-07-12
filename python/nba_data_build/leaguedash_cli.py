"""Build + publish the season-level league-dash datasets.

Scrapes the curated ``leaguedash*`` endpoints (see
:mod:`nba_data_build.scrape.leaguedash`) for NBA + WNBA across a season range,
proxy-rotated and rate-limited through the shared stats.nba.com budget, and
writes one parquet per ``(dataset, season)`` under ``<out>/<tag>/``. With
``--publish`` each ``<tag>`` dir is uploaded to its GitHub release tag on
``sportsdataverse-data`` (one tag per league+endpoint, mirroring the existing
``nba_stats_*`` release convention), so sdv-py ``load_*`` and sdv-db can pull it.

Usage::

    python -m nba_data_build.leaguedash_cli --seasons 2024 2025
    python -m nba_data_build.leaguedash_cli --seasons 2024 --publish
    python -m nba_data_build.leaguedash_cli --seasons 2024 --leagues nba --dry-run
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

from .publish import upload_artifacts
from .scrape.leaguedash import LeagueDashClient, endpoints_for
from .scrape.proxy import RoundRobin, load_proxies
from .scrape.rate_limit import TokenBucket

logger = logging.getLogger(__name__)

_REPO = "sportsdataverse/sportsdataverse-data"
_LEAGUES = ("nba", "wnba")


def _tag(league: str, table: str) -> str:
    """Release tag / dataset name for a league+endpoint, e.g. ``nba_stats_leaguedash_player_stats``."""
    prefix = "nba_stats" if league == "nba" else "wnba_stats"
    return f"{prefix}_leaguedash_{table}"


def build(
    seasons: list[int],
    leagues: list[str],
    out: Path,
    *,
    client: Optional[LeagueDashClient] = None,
) -> dict[str, int]:
    """Scrape each (league, endpoint, season) to ``out/<tag>/<tag>_{season}.parquet``.

    Returns a ``{tag: rows_written}`` summary. A season that yields no rows (or
    errors) is skipped and logged — one bad season never sinks the run.
    """
    if client is None:
        client = LeagueDashClient(RoundRobin(load_proxies()), TokenBucket(n_hits=1))
    written: dict[str, int] = {}
    for league in leagues:
        for ep in endpoints_for(league):
            tag = _tag(league, ep.table)
            for season in seasons:
                try:
                    df = client.fetch(ep, league, season)
                except Exception as exc:  # noqa: BLE001 - best-effort: skip one bad season
                    logger.warning(
                        "leaguedash_skip tag=%s season=%s error=%s",
                        tag,
                        season,
                        str(exc)[:120],
                    )
                    continue
                if df.is_empty():
                    logger.info("leaguedash_empty tag=%s season=%s", tag, season)
                    continue
                dest = out / tag / f"{tag}_{season}.parquet"
                dest.parent.mkdir(parents=True, exist_ok=True)
                df.write_parquet(dest)
                written[tag] = written.get(tag, 0) + df.height
                logger.info(
                    "leaguedash_write tag=%s season=%s rows=%s", tag, season, df.height
                )
    return written


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Build + publish league-dash season datasets."
    )
    ap.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        required=True,
        help="end-year seasons, e.g. 2024 2025",
    )
    ap.add_argument("--leagues", nargs="+", choices=_LEAGUES, default=list(_LEAGUES))
    ap.add_argument("--out", default="build_out/leaguedash", help="output directory")
    ap.add_argument("--repo", default=_REPO, help="release repo")
    ap.add_argument(
        "--publish", action="store_true", help="upload each tag dir to its release"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="plan publish without uploading"
    )
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    out = Path(args.out)
    written = build(args.seasons, args.leagues, out)
    for tag, rows in sorted(written.items()):
        print(f"{tag}: {rows} rows")
    if args.publish or args.dry_run:
        for tag in sorted(written):
            upload_artifacts(out / tag, tag, args.repo, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
