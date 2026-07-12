"""Build + publish the season-level league-dash datasets (full parameter cube).

For each (league, season) this scrapes every curated :class:`Variant`
(player/team stats x measure type, lineups x measure type with 2/3/4/5-man
stacked, the 12 player-tracking categories, bio, standings — Regular Season +
Playoffs stacked and tagged), writes one parquet per ``(table, season)`` under
``<out>/<tag>/``, then assembles the wide **mega tables** (``player_master`` /
``team_master`` / ``lineups_master``) from the granular frames and writes those
too. With ``--publish`` each ``<tag>`` dir is uploaded to its GitHub release tag
on ``sportsdataverse-data`` (asset uploads clobber), so sdv-py ``load_*`` and
sdv-db can pull it.

Usage::

    python -m nba_data_build.leaguedash_cli --seasons 2024 2025
    python -m nba_data_build.leaguedash_cli --seasons 2024 --leagues nba --publish
    python -m nba_data_build.leaguedash_cli --seasons 2024 --dry-run
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import polars as pl

from .publish import upload_artifacts
from .scrape.leaguedash import LeagueDashClient, build_mega, megas, variants
from .scrape.proxy import RoundRobin, load_proxies
from .scrape.rate_limit import TokenBucket

logger = logging.getLogger(__name__)

_REPO = "sportsdataverse/sportsdataverse-data"
_LEAGUES = ("nba", "wnba")


def _tag(league: str, table: str) -> str:
    """Release tag for a league table, e.g. ``nba_stats_leaguedash_player_stats_base``."""
    prefix = "nba_stats" if league == "nba" else "wnba_stats"
    return f"{prefix}_leaguedash_{table}"


def _write(out: Path, tag: str, season: int, df: pl.DataFrame) -> None:
    dest = out / tag / f"{tag}_{season}.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(dest)


def build(
    seasons: list[int],
    leagues: list[str],
    out: Path,
    *,
    client: LeagueDashClient | None = None,
) -> dict[str, int]:
    """Scrape the full cube to ``out/<tag>/<tag>_{season}.parquet`` (+ megas).

    Returns ``{tag: rows_written}``. A variant-season that errors is skipped and
    logged (best-effort — one bad corner never sinks the run); megas assemble
    from whatever granular frames landed.
    """
    if client is None:
        client = LeagueDashClient(RoundRobin(load_proxies()), TokenBucket(n_hits=1))
    written: dict[str, int] = {}
    for league in leagues:
        for season in seasons:
            frames: dict[str, pl.DataFrame] = {}
            for v in variants(league):
                tag = _tag(league, v.table)
                try:
                    df = client.fetch_variant(v, league, season)
                except Exception as exc:  # noqa: BLE001 - best-effort: skip one bad corner
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
                frames[v.table] = df
                _write(out, tag, season, df)
                written[tag] = written.get(tag, 0) + df.height
                logger.info("leaguedash_write tag=%s season=%s rows=%s", tag, season, df.height)
            for mega in megas(league):
                mdf = build_mega(mega, league, frames)
                if mdf is None or mdf.is_empty():
                    continue
                tag = _tag(league, mega)
                _write(out, tag, season, mdf)
                written[tag] = written.get(tag, 0) + mdf.height
                logger.info(
                    "leaguedash_mega tag=%s season=%s rows=%s cols=%s",
                    tag,
                    season,
                    mdf.height,
                    mdf.width,
                )
    return written


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Build + publish league-dash season datasets.")
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
    ap.add_argument("--publish", action="store_true", help="upload each tag dir to its release")
    ap.add_argument("--dry-run", action="store_true", help="plan publish without uploading")
    return ap


def main(argv: list[str] | None = None) -> int:
    # long proxied job: make per-table progress visible in the redirected log
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
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
