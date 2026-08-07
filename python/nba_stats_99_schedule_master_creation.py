"""Stage 99 — schedule master, games-in-data-repo manifest, and coverage index.

Runs LAST in the daily processor, after every dataset is built. Thin shim over
``nba_data_build.master``; emits both D34 artifacts from one in-memory frame so
they cannot drift:

* ``nba_stats/nba_stats_schedule_master.parquet`` — every game the schedule
  knows about (the denominator).
* ``nba_stats/nba_stats_games_in_data_repo.parquet`` — only games with >=1
  ``in_*`` flag true (the numerator; what consumers join against).
* ``nba_stats/nba_stats_schedule_coverage.parquet`` — one row per
  (season, season_type_id) with per-dataset build coverage.

The ``in_*`` flag set is derived from the ``DATASETS`` registry
(``level == "game"``) and is stamped into the committed per-season schedule
files — the origin of every flag — by one of two sources:

* ``--built-dir <out> --season <end_year>``: this run's built artifacts
  (exact; used in-loop by ``daily_nba_stats_python_processor.sh``).
* ``--raw-root <json base>``: raw-store presence of each dataset's source
  endpoint (faithful proxy — the reshaper is a pure function of the raw
  store; used for full-history backfills on a machine with the -raw sibling).

Stage 99 is not a dataset shim: it has no registry entry and no ``DATASET``
constant. Number 99 is reserved for the schedule master (spec D16/D34).

Example:
    Union the committed season schedules into the master + manifest::

        uv run python python/nba_stats_99_schedule_master_creation.py

    Restamp every season from the local -raw sibling, then rebuild::

        uv run python python/nba_stats_99_schedule_master_creation.py \
            --raw-root ../hoopR-nba-stats-raw/nba_stats/json
"""

from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl
from nba_data_build.master import (
    build_coverage,
    build_master,
    games_in_data_repo,
    raw_store_game_ids,
    stamp_from_built,
    stamp_from_raw,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
LEAGUE = "nba_stats"


def _span(end_year: int) -> str:
    """End-year (repo convention: 2026 = 2025-26) -> the yearly-file span label."""
    return f"{end_year - 1}-{str(end_year)[-2:]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default=str(REPO_ROOT / LEAGUE), help="dataset tree root")
    parser.add_argument("--built-dir", default=None, help="reshape --out dir to restamp from")
    parser.add_argument("--season", type=int, default=None, help="end-year season for --built-dir")
    parser.add_argument(
        "--raw-root", default=None, help="raw json base to restamp every season from"
    )
    parser.add_argument(
        "--stamp-only",
        action="store_true",
        help="restamp season files without rebuilding the master (in-loop use)",
    )
    args = parser.parse_args(argv)

    base = Path(args.base)
    season_dir = base / "schedules" / "parquet"
    paths = sorted(season_dir.glob("schedule_*.parquet"))
    if not paths:
        print(f"::error ::no season schedules under {season_dir}")
        return 1

    if args.built_dir is not None:
        if args.season is None:
            print("::error ::--built-dir requires --season <end_year>")
            return 1
        target = season_dir / f"schedule_{_span(args.season)}.parquet"
        if not target.is_file():
            print(f"::warning ::no season schedule at {target}; nothing to restamp")
        else:
            stamped = stamp_from_built(pl.read_parquet(target), args.built_dir, args.season)
            stamped.write_parquet(target)
            print(f"restamped {target.name} from {args.built_dir}")
    elif args.raw_root is not None:
        endpoint_gids = raw_store_game_ids(args.raw_root)
        for path in paths:
            stamp_from_raw(pl.read_parquet(path), endpoint_gids).write_parquet(path)
        print(f"restamped {len(paths)} season file(s) from raw store {args.raw_root}")

    if args.stamp_only:
        return 0

    master = build_master(
        [pl.read_parquet(p) for p in sorted(season_dir.glob("schedule_*.parquet"))]
    )
    manifest = games_in_data_repo(master)
    coverage = build_coverage(master)

    for frame, path in (
        (master, base / f"{LEAGUE}_schedule_master.parquet"),
        (manifest, base / f"{LEAGUE}_games_in_data_repo.parquet"),
        (coverage, base / f"{LEAGUE}_schedule_coverage.parquet"),
    ):
        frame.write_parquet(path)

    print(f"master:   {master.height} games across {len(paths)} seasons")
    print(f"manifest: {manifest.height} games in >=1 compilation")
    print(f"coverage: {coverage.height} rows")
    for flag in sorted(c for c in master.columns if c.startswith("in_")):
        print(f"  {flag}: {master[flag].sum()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
