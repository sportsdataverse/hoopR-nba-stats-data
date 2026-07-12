"""Build + publish the season-level league-dash datasets (full parameter cube).

NBA-only (the WNBA half moved to wehoop-wnba-stats-data's python/wnba_data_build/
— WNBA has its own producer repo, mirroring the hoopR/wehoop R-package split).

For each season this scrapes every curated :class:`Variant` (player/team stats
x measure type, lineups x measure type with 2/3/4/5-man stacked, the 12
player-tracking categories, bio, standings — Regular Season + Playoffs stacked
and tagged), assembles the wide **mega tables** (``player_master`` /
``team_master`` / ``lineups_master``), and writes one parquet per
``(table, season)`` as an **asset** inside the ``nba_stats_leaguedash`` release.

With ``--publish`` the output dir is uploaded to that tag (asset uploads
clobber), so sdv-py ``load_*`` and sdv-db pull by asset name.

Usage::

    python -m nba_data_build.leaguedash_cli --seasons 2024 2025
    python -m nba_data_build.leaguedash_cli --seasons 2024 --publish
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
_TAG = "nba_stats_leaguedash"


def _write(out: Path, table: str, season: int, df: pl.DataFrame) -> None:
    dest = out / _TAG / f"{table}_{season}.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(dest)


def build(
    seasons: list[int],
    out: Path,
    *,
    client: Optional[LeagueDashClient] = None,
) -> dict[str, int]:
    """Scrape the full cube into the release dir (+ megas).

    Writes ``out/nba_stats_leaguedash/<table>_<season>.parquet`` for every
    table and returns ``{"nba_stats_leaguedash/<table>": rows}``. A
    variant-season that errors is skipped and logged (best-effort — one bad
    corner never sinks the run); megas assemble from whatever granular
    frames landed.
    """
    if client is None:
        client = LeagueDashClient(RoundRobin(load_proxies()), TokenBucket(n_hits=1))
    written: dict[str, int] = {}
    for season in seasons:
        frames: dict[str, pl.DataFrame] = {}
        for v in variants():
            try:
                df = client.fetch_variant(v, season)
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
            _write(out, v.table, season, df)
            written[f"{_TAG}/{v.table}"] = (
                written.get(f"{_TAG}/{v.table}", 0) + df.height
            )
            logger.info(
                "leaguedash_write table=%s season=%s rows=%s",
                v.table,
                season,
                df.height,
            )
        # megas assemble from DISK state, not just this run's frames: a
        # partial re-run (skipped tables keep their prior files) then
        # converges to the full-width mega instead of overwriting it
        # with a narrow one built from whatever happened to scrape.
        for v in variants():
            prior = out / _TAG / f"{v.table}_{season}.parquet"
            if prior.exists():
                frames[v.table] = pl.read_parquet(prior)
        for mega in megas():
            mdf = build_mega(mega, frames)
            if mdf is None or mdf.is_empty():
                continue
            _write(out, mega, season, mdf)
            written[f"{_TAG}/{mega}"] = written.get(f"{_TAG}/{mega}", 0) + mdf.height
            logger.info(
                "leaguedash_mega table=%s season=%s rows=%s cols=%s",
                mega,
                season,
                mdf.height,
                mdf.width,
            )
    return written


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Build + publish NBA league-dash season datasets."
    )
    ap.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        required=True,
        help="end-year seasons, e.g. 2024 2025",
    )
    ap.add_argument("--out", default="build_out/leaguedash", help="output directory")
    ap.add_argument("--repo", default=_REPO, help="release repo")
    ap.add_argument(
        "--publish", action="store_true", help="upload the league dir to its release"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="plan publish without uploading"
    )
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    # long proxied job: make per-table progress visible in the redirected log
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    args = _parser().parse_args(argv)
    out = Path(args.out)
    written = build(args.seasons, out)
    for key, rows in sorted(written.items()):
        print(f"{key}: {rows} rows")
    if (args.publish or args.dry_run) and (out / _TAG).exists():
        upload_artifacts(out / _TAG, _TAG, args.repo, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
