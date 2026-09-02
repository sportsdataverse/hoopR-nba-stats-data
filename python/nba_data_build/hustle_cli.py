"""``python -m nba_data_build.hustle_cli`` -- compile ``nba_stats_hustle``.

The NBA's hustle box score: contested shots, deflections, charges drawn, screen
assists, loose balls recovered, box outs. Two season-level endpoints, captured
into ``hoopR-nba-stats-raw`` on 2026-09-02 and compiled here for the first time.

``leaguehustlestatsplayer``
    One row per player-season (28 columns).
``leaguehustlestatsteam``
    The same measures rolled up to the team (20 columns).

Both use ``{season}/{season_type}_{per_mode}.json``, the same layout as the two
matchup endpoints, so this is ``matchups_cli`` with the endpoint names and the
floor swapped -- ``raw_compile`` already owns the parse, the empty-payload skip
and the stamp.

**Not included: ``hustlestatsboxscore``.** It is the PER-GAME half of the family
(~14,500 payloads, ~290 MB) and is not captured yet. It returns the plain
``resultSets`` envelope, so it needs no new builder code when it lands -- it
belongs with the repo's per-game reshape, not this season compile.

Makes no network calls -- every payload is already in the raw store.

Example::

    python -m nba_data_build.hustle_cli --seasons 2024 2025
    python -m nba_data_build.hustle_cli --seasons 2024 --publish
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

_TAG = "nba_stats_hustle"
_ENDPOINTS = ("leaguehustlestatsplayer", "leaguehustlestatsteam")

#: Probed live 2026-09-02, on the endpoints themselves rather than on what
#: happened to be captured: 2013-14 and 2014-15 answer a valid envelope with an
#: empty rowSet, 2015-16 is the first season with rows. 2015 is therefore the
#: floor -- but see ``_thin`` below, which is where 2015-16 actually splits.
FIRST_SEASON = 2015
LAST_SEASON = 2025

#: 2015-16 REGULAR SEASON is two games, not a season.
#:
#: Measured on the compiled frames: ``leaguehustlestatsplayer`` 2015-16 regular
#: season is 147 players across 15 teams with ``max(g) == 2`` -- the NBA's
#: pre-launch trial, 2 of that season's 1,230 games. Its PLAYOFFS half is
#: complete (211 players, all 16 teams, ``max(g) == 24``), which is consistent
#: with the league having launched hustle tracking at the 2016 playoffs.
#:
#: The empty-payload guard cannot catch this: 147 rows is not an empty frame, so
#: it would write ``leaguehustlestatsplayer_regular-season_totals_2015.parquet``
#: -- an asset a consumer reads as the 2015-16 regular season and gets 256
#: league-wide deflections for, against 38,174 the following year. That is the
#: 84 schema-only ``ncaa_baseball`` assets (ledger L54) wearing a different
#: costume, and the same call the ``game_matchups`` 2016 floor made at 1.5%
#: coverage.
#:
#: Scoped to the season TYPE rather than the season, because dropping the whole
#: of 2015 would throw away a complete playoffs. The raw store still holds all
#: four 2015 variants -- the capture records what upstream served, and this is
#: the publish decision layered on top.
_THIN = {(2015, "regular-season")}


def _thin(season: int, stem: str) -> bool:
    """True for a variant that is populated but too thin to be its own name."""
    return (season, stem.split("_", 1)[0]) in _THIN


def build(seasons: list[int], out: Path, *, raw: Optional[Path] = None) -> dict[str, int]:
    """Compile both hustle endpoints into ``out/nba_stats_hustle/``.

    Asset names are prefixed with the endpoint so the two never collide, e.g.
    ``leaguehustlestatsplayer_regular-season_totals_2024.parquet``.
    """
    raw = raw or raw_root()
    # once, before any endpoint: this tag carries two, and clearing per endpoint
    # would delete the previous one's freshly written assets
    clear_seasons(out, _TAG, seasons)
    written: dict[str, int] = {}
    for endpoint in _ENDPOINTS:
        written.update(
            compile_season_dirs(
                raw,
                endpoint,
                seasons,
                out,
                _TAG,
                stamp=stamp_season_type_per_mode,
                prefix=f"{endpoint}_",
                skip=_thin,
            )
        )
    return written


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nba_data_build.hustle_cli")
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
