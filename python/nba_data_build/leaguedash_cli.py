"""Build + publish the season-level league-dash datasets (full parameter cube).

For each (league, season) this scrapes every curated :class:`Variant`
(player/team stats x measure type, lineups x measure type with 2/3/4/5-man
stacked, the 12 player-tracking categories, bio, standings — Regular Season +
Playoffs stacked and tagged), assembles the wide **mega tables**
(``player_master`` / ``team_master`` / ``lineups_master``), and writes one
parquet per ``(table, season)`` as an **asset** inside a single per-league
release dir.

Release layout is **consolidated to one tag per league** —
``nba_stats_leaguedash`` and ``wnba_stats_leaguedash`` on ``sportsdataverse-data``
— each holding every table's per-season assets (``<table>_<season>.parquet``),
rather than a tag per table. With ``--publish`` each league dir is uploaded to
its tag (asset uploads clobber), so sdv-py ``load_*`` and sdv-db pull by asset
name.

Usage::

    python -m nba_data_build.leaguedash_cli --seasons 2024 2025
    python -m nba_data_build.leaguedash_cli --seasons 2024 --leagues nba --publish
    python -m nba_data_build.leaguedash_cli --seasons 2024 --dry-run
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

import polars as pl

from .publish import upload_artifacts
from .scrape.leaguedash import LeagueDashClient, build_mega, megas, variants
from .scrape.proxy import RoundRobin, load_proxies
from .scrape.rate_limit import TokenBucket

logger = logging.getLogger(__name__)

_REPO = "sportsdataverse/sportsdataverse-data"
_LEAGUES = ("nba", "wnba")


def league_tag(league: str) -> str:
    """The single consolidated release tag for a league's league-dash data."""
    return f"{'nba_stats' if league == 'nba' else 'wnba_stats'}_leaguedash"


def _write(out: Path, tag: str, table: str, season: int, df: pl.DataFrame) -> None:
    dest = out / tag / f"{table}_{season}.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(dest)


def build(
    seasons: list[int],
    leagues: list[str],
    out: Path,
    *,
    client: Optional[LeagueDashClient] = None,
) -> dict[str, int]:
    """Scrape the full cube into per-league release dirs (+ megas).

    Writes ``out/<league_tag>/<table>_<season>.parquet`` for every table and
    returns ``{"<league_tag>/<table>": rows}``. A variant-season that errors is
    skipped and logged (best-effort — one bad corner never sinks the run); megas
    assemble from whatever granular frames landed.
    """
    if client is None:
        client = LeagueDashClient(RoundRobin(load_proxies()), TokenBucket(n_hits=1))
    written: dict[str, int] = {}
    for league in leagues:
        tag = league_tag(league)
        for season in seasons:
            frames: dict[str, pl.DataFrame] = {}
            for v in variants(league):
                try:
                    df = client.fetch_variant(v, league, season)
                except Exception as exc:  # noqa: BLE001 - best-effort: skip one bad corner
                    logger.warning(
                        "leaguedash_skip table=%s season=%s error=%s",
                        v.table,
                        season,
                        str(exc)[:120],
                    )
                    continue
                if df.is_empty():
                    logger.info("leaguedash_empty table=%s season=%s", v.table, season)
                    continue
                frames[v.table] = df
                _write(out, tag, v.table, season, df)
                written[f"{tag}/{v.table}"] = written.get(f"{tag}/{v.table}", 0) + df.height
                logger.info("leaguedash_write table=%s season=%s rows=%s", v.table, season, df.height)
            for mega in megas(league):
                mdf = build_mega(mega, league, frames)
                if mdf is None or mdf.is_empty():
                    continue
                _write(out, tag, mega, season, mdf)
                written[f"{tag}/{mega}"] = written.get(f"{tag}/{mega}", 0) + mdf.height
                logger.info(
                    "leaguedash_mega table=%s season=%s rows=%s cols=%s",
                    mega,
                    season,
                    mdf.height,
                    mdf.width,
                )
    return written


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Build + publish league-dash season datasets.")
    ap.add_argument("--seasons", type=int, nargs="+", required=True, help="end-year seasons, e.g. 2024 2025")
    ap.add_argument("--leagues", nargs="+", choices=_LEAGUES, default=list(_LEAGUES))
    ap.add_argument("--out", default="build_out/leaguedash", help="output directory")
    ap.add_argument("--repo", default=_REPO, help="release repo")
    ap.add_argument("--publish", action="store_true", help="upload each league dir to its release")
    ap.add_argument("--dry-run", action="store_true", help="plan publish without uploading")
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    # long proxied job: make per-table progress visible in the redirected log
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parser().parse_args(argv)
    out = Path(args.out)
    written = build(args.seasons, args.leagues, out)
    for key, rows in sorted(written.items()):
        print(f"{key}: {rows} rows")
    if args.publish or args.dry_run:
        for league in args.leagues:
            tag = league_tag(league)
            if (out / tag).exists():
                upload_artifacts(out / tag, tag, args.repo, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
