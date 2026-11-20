"""``python -m nba_data_build.matchups_cli`` -- compile ``nba_stats_matchups``.

Two season-level endpoints, both captured and neither ever compiled:

``leagueseasonmatchups``
    Player-vs-player season totals -- one row per (offensive player, defensive
    player) pair.
``matchupsrollup``
    The same matchups rolled up by defensive position.

Both use ``{season}/{season_type}_{per_mode}.json`` (``season`` = END year, which
is also the asset year), so one tag carries both with an endpoint prefix on the
asset name.

**Playoffs ``leagueseasonmatchups`` are derived from ``boxscorematchupsv3``.**
stats.nba.com serves no playoff rows for that endpoint (measured 2026-11-20 from
a residential IP: 0 rows with blank or per-team filters, HTTP 500 for every
``PORound``), so its ``playoffs_*`` payloads are empty envelopes. When one is,
:func:`playoff_matchups` sums the season's playoff games (game id ``004…``) into
the same columns. Measured on 2024-25 regular season, the same sum over the 1,230
``002…`` games reproduces all 141,255 official pairs: every counting stat, GP and
``partial_poss`` exact except one pair, ``matchup_min`` within one second (the
official string does not round its own ``matchup_time_sec`` consistently either),
and 17 rows where the official name is an upstream typo; 2025-26 regular season
is exact on every pair too. Derived playoffs, summed per defender, equal
``matchupsrollup``'s ``TOTAL`` row for 2018-2025 (2024-25 grand totals within 2
points). They do not for 2025-26, because the rollup itself stops agreeing with
the official pair table that season (214,006 vs 240,091 regular-season FGA), while
the per-game sum still matches the pair table exactly. ``matchupsrollup`` is NOT a
substitute in any season: it is defender x offensive position, with no offensive
player.

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

import polars as pl

from .publish import upload_artifacts
from .raw_compile import (
    REPO,
    clear_seasons,
    compile_season_dirs,
    read_result_sets,
    stamp_season_type_per_mode,
    write_asset,
)
from .reshape import raw as raw_store
from .reshape.build import build_matchups
from .synergy_cli import raw_root

logger = logging.getLogger(__name__)

_TAG = "nba_stats_matchups"
_ENDPOINTS = ("leagueseasonmatchups", "matchupsrollup")

#: Measured 2026-09-02: both endpoints return rows for 2017-18..2025-26 only
#: (END years 2018-2026). 1996-97..2005-06 and the in-progress season hold
#: payloads with an empty rowSet.
FIRST_SEASON = 2018
LAST_SEASON = 2026

#: season-table column <- per-game ``boxscorematchupsv3`` statistic (snake_cased).
#: ``matchup_minutes_sort`` is seconds, despite the name.
_SUMS = {
    "partial_poss": "partial_possessions",
    "player_pts": "player_points",
    "team_pts": "team_points",
    "matchup_ast": "matchup_assists",
    "matchup_tov": "matchup_turnovers",
    "matchup_blk": "matchup_blocks",
    "matchup_fgm": "matchup_field_goals_made",
    "matchup_fga": "matchup_field_goals_attempted",
    "matchup_fg3_m": "matchup_three_pointers_made",
    "matchup_fg3_a": "matchup_three_pointers_attempted",
    "help_blk": "help_blocks",
    "help_fgm": "help_field_goals_made",
    "help_fga": "help_field_goals_attempted",
    "matchup_ftm": "matchup_free_throws_made",
    "matchup_fta": "matchup_free_throws_attempted",
    "sfl": "shooting_fouls",
    "matchup_time_sec": "matchup_minutes_sort",
}
#: averaged by the pergame table; help_* stay totals there (and are 0 in both sources)
_PER_GAME = [c for c in _SUMS if not c.startswith("help_") and c != "matchup_time_sec"]
#: the official table rounds half-up (13/16 -> 0.813); polars' default is half-to-even
_HALF = "half_away_from_zero"


def _pct(made: str, att: str) -> pl.Expr:
    return (
        pl.when(pl.col(att) > 0)
        .then((pl.col(made) / pl.col(att)).round(3, mode=_HALF))
        .otherwise(0.0)
    )


def playoff_matchups(raw: Path, season: int) -> dict[str, pl.DataFrame]:
    """``{"playoffs_totals": ..., "playoffs_pergame": ...}`` summed from the season's playoff games.

    Empty dict when no playoff game carries matchups. Columns and dtypes follow the
    season's regular-season payloads, so the two concatenate.
    """
    games = [
        g for g in raw_store.available_games(raw, "boxscorematchupsv3", season) if g[2:3] == "4"
    ]
    per_game = build_matchups(raw, season, games) if games else pl.DataFrame()
    if not per_game.height:
        return {}
    # SEASON_ID is season-type digit + START year; the game id carries both (004 24 ...)
    season_id = f"4{2000 + int(games[0][3:5])}"
    name = lambda side: pl.concat_str(  # noqa: E731
        [pl.col(f"{side}_first_name"), pl.col(f"{side}_family_name")], separator=" "
    ).first()
    t = per_game.group_by("off_person_id", "def_person_id").agg(
        off_player_name=name("off"),
        def_player_name=name("def"),
        gp=pl.col("game_id").n_unique().cast(pl.Int64),
        **{k: pl.col(v).sum() for k, v in _SUMS.items()},
    )
    sec = pl.col("matchup_time_sec").round(0, mode=_HALF).cast(pl.Int64)
    totals = t.select(
        season_id=pl.lit(season_id),
        off_player_id="off_person_id",
        off_player_name="off_player_name",
        def_player_id="def_person_id",
        def_player_name="def_player_name",
        gp="gp",
        matchup_min=pl.format("{}:{}", sec // 60, (sec % 60).cast(pl.String).str.zfill(2)),
        partial_poss=pl.col("partial_poss").round(1, mode=_HALF),
        player_pts="player_pts",
        team_pts="team_pts",
        matchup_ast="matchup_ast",
        matchup_tov="matchup_tov",
        matchup_blk="matchup_blk",
        matchup_fgm="matchup_fgm",
        matchup_fga="matchup_fga",
        matchup_fg_pct=_pct("matchup_fgm", "matchup_fga"),
        matchup_fg3_m="matchup_fg3_m",
        matchup_fg3_a="matchup_fg3_a",
        matchup_fg3_pct=_pct("matchup_fg3_m", "matchup_fg3_a"),
        help_blk="help_blk",
        help_fgm="help_fgm",
        help_fga="help_fga",
        help_fg_perc=_pct("help_fgm", "help_fga"),
        matchup_ftm="matchup_ftm",
        matchup_fta="matchup_fta",
        sfl="sfl",
        matchup_time_sec=pl.col("matchup_time_sec").round(1, mode=_HALF),
    ).sort("off_player_id", "def_player_id")
    gp = pl.col("gp")
    pergame = totals.with_columns(
        matchup_min=(pl.col("matchup_time_sec") / 60 / gp).round(1, mode=_HALF),
        **{c: (pl.col(c) / gp).round(1, mode=_HALF) for c in _PER_GAME},
    ).drop("matchup_time_sec")
    frames = {"playoffs_totals": totals, "playoffs_pergame": pergame}
    for stem, frame in frames.items():
        reg = read_result_sets(
            raw
            / "leagueseasonmatchups"
            / str(season)
            / f"{stem.replace('playoffs', 'regular-season')}.json"
        )
        if reg.height:  # ponytail: help_fg_perc is Int64 there only because it is always 0
            frames[stem] = frame.select(reg.columns).cast(dict(reg.schema))
    return frames


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
                raw,
                endpoint,
                seasons,
                out,
                _TAG,
                stamp=stamp_season_type_per_mode,
                prefix=f"{endpoint}_",
            )
        )
    for season in seasons:
        # clear_seasons ran above, so an existing file came from a real payload THIS run
        done = [
            (out / _TAG / f"leagueseasonmatchups_playoffs_{m}_{season}.parquet").exists()
            for m in ("totals", "pergame")
        ]
        if all(done):
            continue
        for stem, frame in playoff_matchups(raw, season).items():
            name = f"leagueseasonmatchups_{stem}"
            if (out / _TAG / f"{name}_{season}.parquet").exists():
                continue
            write_asset(
                out, _TAG, f"{name}_{season}", stamp_season_type_per_mode(frame, season, stem)
            )
            key = f"{_TAG}/{name}"
            written[key] = written.get(key, 0) + frame.height
            logger.info(
                "derived_write asset=%s season=%s rows=%s source=boxscorematchupsv3",
                name,
                season,
                frame.height,
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
