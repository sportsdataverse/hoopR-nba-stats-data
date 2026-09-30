"""Stage 99 — schedule master, games-in-data-repo manifest, and coverage index.

Runs LAST in the daily processor, after every season's parquets are committed
into the tree. Thin shim over ``nba_data_build.master``; emits all three D34
artifacts from one in-memory frame so they cannot drift:

* ``nba_stats/nba_stats_schedule_master.parquet`` — every game the schedule
  knows about (the denominator).
* ``nba_stats/nba_stats_games_in_data_repo.parquet`` — only games with >=1
  ``in_*`` flag true (the numerator; what consumers join against).
* ``nba_stats/nba_stats_schedule_coverage.parquet`` — one row per
  (season, season_type_id) with per-dataset build coverage.

Rows come from the raw store's ``scheduleleaguev2/{E}.json`` for every END-year
season present (``--raw-root``: a local json base or a raw.githubusercontent
URL), ``season`` stamped as the END-year Int. Flags come from the committed tree
under ``--base`` (``master.FLAG_SOURCES``). Nothing is read from the retired
``schedules/parquet/schedule_{E}`` family.

Stage 99 is not a dataset shim: it has no registry entry and no ``DATASET``
constant. Number 99 is reserved for the schedule master (spec D16/D34).

Example:
    Rebuild from the sibling -raw checkout::

        uv run python python/nba_stats_99_schedule_master_creation.py

    Or straight from GitHub::

        uv run python python/nba_stats_99_schedule_master_creation.py \
            --raw-root https://raw.githubusercontent.com/sportsdataverse/hoopR-nba-stats-raw/main/nba_stats/json
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from nba_data_build.master import (
    build_coverage,
    build_master,
    games_in_data_repo,
    season_schedule,
    stamp_from_tree,
)
from nba_data_build.reshape.raw import read_season

REPO_ROOT = Path(__file__).resolve().parents[1]
LEAGUE = "nba_stats"
FIRST_SEASON = 1997  # 1996-97, the start of the stats.nba.com history


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default=str(REPO_ROOT / LEAGUE), help="dataset tree root")
    parser.add_argument(
        "--raw-root",
        default=str(REPO_ROOT.parent / "hoopR-nba-stats-raw" / LEAGUE / "json"),
        help="raw json base (local dir or http(s) URL) holding scheduleleaguev2/{E}.json",
    )
    args = parser.parse_args(argv)

    base = Path(args.base)
    # Probe rather than list: a URL root cannot be enumerated, and an absent
    # season is a clean None (404 / missing file). Next year's schedule is
    # published before the season starts, hence the +1.
    frames = []
    for season in range(FIRST_SEASON, date.today().year + 2):
        payload = read_season(args.raw_root, "scheduleleaguev2", season)
        frame = season_schedule(payload, season) if payload is not None else None
        if frame is None or frame.is_empty():
            continue
        frames.append(stamp_from_tree(frame, base, season))
    if not frames:
        print(f"::error ::no scheduleleaguev2 seasons under {args.raw_root}")
        return 1

    master = build_master(frames)
    manifest = games_in_data_repo(master)
    coverage = build_coverage(master)

    for frame, path in (
        (master, base / f"{LEAGUE}_schedule_master.parquet"),
        (manifest, base / f"{LEAGUE}_games_in_data_repo.parquet"),
        (coverage, base / f"{LEAGUE}_schedule_coverage.parquet"),
    ):
        frame.write_parquet(path)

    print(f"master:   {master.height} games across {len(frames)} seasons")
    print(f"manifest: {manifest.height} games in >=1 compilation")
    print(f"coverage: {coverage.height} rows")
    for flag in sorted(c for c in master.columns if c.startswith("in_")):
        print(f"  {flag}: {master[flag].sum()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
