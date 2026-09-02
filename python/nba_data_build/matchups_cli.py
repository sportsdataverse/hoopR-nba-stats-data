"""``python -m nba_data_build.matchups_cli`` -- compile ``nba_stats_matchups``.

Two season-level endpoints, both captured and neither ever compiled:

``leagueseasonmatchups``
    Player-vs-player season totals -- one row per (offensive player, defensive
    player) pair.
``matchupsrollup``
    The same matchups rolled up by defensive position.

Both use ``{season}/{season_type}_{per_mode}.json``, so one tag carries both with
an endpoint prefix on the asset name.

**Not included: ``boxscorematchupsv3``.** It is 25,732 PER-GAME payloads in the v3
envelope (``{meta, boxScoreMatchups}``), not the ``resultSets`` shape these two
use, so it belongs with the repo's per-game v3 reshape rather than a season
compile. Tracked separately.

Makes no network calls -- every payload is already in the raw store.

Example::

    python -m nba_data_build.matchups_cli --seasons 2024 2025
    python -m nba_data_build.matchups_cli --seasons 2024 --publish
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional

from .publish import upload_artifacts
from .raw_compile import (
    REPO,
    clear_seasons,
    compile_season_dirs,
    stamp_season_type_per_mode,
)
from .synergy_cli import raw_root

logger = logging.getLogger(__name__)

_TAG = "nba_stats_matchups"
_ENDPOINTS = ("leagueseasonmatchups", "matchupsrollup")

#: Measured 2026-09-02: both endpoints return rows for 2017-2025 only.
#: 1996-2005 and the in-progress season hold payloads with an empty rowSet.
FIRST_SEASON = 2017
LAST_SEASON = 2025

def build(seasons: list[int], out: Path, *, raw: Optional[Path] = None) -> dict[str, int]:
    """Compile both matchup endpoints into ``out/nba_stats_matchups/``.

    Asset names are prefixed with the endpoint so the two never collide, e.g.
    ``leagueseasonmatchups_regular-season_totals_2024.parquet``.
    """
    raw = raw or raw_root()
    # once, before any endpoint: a tag can carry several endpoints and clearing
    # per endpoint would delete the previous one's freshly written assets
    clear_seasons(out, _TAG, seasons)
    written: dict[str, int] = {}
    for endpoint in _ENDPOINTS:
        written.update(
            compile_season_dirs(
                raw, endpoint, seasons, out, _TAG, stamp=stamp_season_type_per_mode, prefix=f"{endpoint}_"
            )
        )
    return written


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nba_data_build.matchups_cli")
    p.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        default=list(range(FIRST_SEASON, LAST_SEASON + 1)),
        help=f"seasons to compile (default {FIRST_SEASON}-{LAST_SEASON}, the ones with rows)",
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
