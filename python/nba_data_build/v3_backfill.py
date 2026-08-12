"""Program V (design §9) v3 backfill: compile D26b-named season parquets into staging.

Builds the four v3 families -- ``schedule`` / ``play_by_play`` / ``possessions`` /
``lineups`` -- for a range of seasons entirely from the committed raw store
(``hoopR-nba-stats-raw``), no network. Output goes to a **staging** directory
(default ``{repo}/v3_staging``, gitignored) with the D26b cutover names::

    nba_schedule_2006.parquet        # 2005-06 season -- END-year, no _v3
    nba_play_by_play_2006.parquet
    nba_possessions_2006.parquet
    nba_lineups_2006.parquet

The committed tree is untouched until the section-9.3 gate (:mod:`.v3_gate`)
passes; the cutover move + tag swap (D26d) is a separate operator decision.

Season convention: CLI seasons are **END years** (2006 = the 2005-06 season),
matching the raw store's game-endpoint directories. ``leaguegamelog`` and
``scheduleleaguev2`` season dirs/files are keyed by START year (end - 1).

Game universe: **every** season type, not just the two ``leaguegamelog`` was
captured at. ``leaguegamelog`` (regular-season + playoffs) stays the metadata
source where it has a game; ``scheduleleaguev2`` supplies the ids it never
covered -- preseason (``001``), All-Star (``003``), play-in (``005``) and the
NBA Cup final (``006``). Older eras legitimately lack the later types (no
play-in before 2020-21, no NBA Cup before 2023-24).

Resumability is two-level: the per-game frame cache is shared with
``pipeline_cli`` (``{repo}/.nba_pipeline_cache``), and a season whose four
staged parquets already exist is skipped entirely unless ``--rebuild``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

import polars as pl

from .process.datasets import (
    ProcessedGame,
    _coerce_id_dtypes,
    _read_game_cache,
    write_game_cache,
)
from .process.from_raw import process_game
from .scrape.raw_store import resolve_raw_path

FAMILIES = ("schedule", "play_by_play", "possessions", "lineups")

#: ProcessedGame attribute backing each non-schedule family.
_FRAME_OF = {
    "play_by_play": "enriched_pbp",
    "possessions": "possessions",
    "lineups": "lineups",
}

#: The only two season types ``leaguegamelog`` was ever captured at. Everything
#: else (preseason / All-Star / play-in / NBA Cup final) reaches the universe via
#: :func:`schedule_from_league_schedule` instead.
_GAMELOG_VARIANTS = ("regular-season", "playoffs")

#: game-id digit 3 -> ``season_type`` slug. The two gamelog slugs are kept verbatim
#: so existing rows don't change value; the four new ones follow the same style.
#: (The sibling raw-repo ``schedule_master`` uses underscored labels -- a
#: pre-existing divergence, not introduced here.)
SEASON_TYPE_OF_PREFIX = {
    "1": "preseason",
    "2": "regular-season",
    "3": "all-star",
    "4": "playoffs",
    "5": "play-in",
    "6": "nba-cup",
}

#: ``gameStatus`` in ``scheduleleaguev2`` meaning the game was played to a final.
_GAME_STATUS_FINAL = 3


def _log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{stamp}] {msg}", flush=True)


def repo_root_default() -> Path:
    """Repo root inferred from this file (…/python/nba_data_build/v3_backfill.py)."""
    return Path(__file__).resolve().parents[2]


def season_paths(staging: Union[str, Path], season_end: int) -> dict[str, Path]:
    """D26b staged parquet path per family for one END-year season."""
    staging = Path(staging)
    return {fam: staging / f"nba_{fam}_{season_end}.parquet" for fam in FAMILIES}


def season_done(staging: Union[str, Path], season_end: int) -> bool:
    """True when all four staged parquets exist (the resume checkpoint)."""
    return all(p.exists() for p in season_paths(staging, season_end).values())


def _read_gamelog(
    raw_root: Union[str, Path], season_end: int
) -> list[tuple[str, list[str], list[list[Any]]]]:
    """(season_type, headers, team rows) per captured leaguegamelog variant."""
    out = []
    for variant in _GAMELOG_VARIANTS:
        path = (
            Path(raw_root)
            / "nba_stats"
            / "json"
            / "leaguegamelog"
            / str(season_end - 1)
            / f"{variant}.json"
        )
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for rs in payload.get("resultSets") or []:
            headers = [str(h).upper() for h in rs.get("headers") or []]
            if "GAME_ID" in headers:
                out.append((variant, headers, rs.get("rowSet") or []))
                break
    return out


_SCHEDULE_SCHEMA: dict[str, type[pl.DataType]] = {
    "game_id": pl.Utf8,
    "season": pl.Int64,
    "season_type": pl.Utf8,
    "game_date": pl.Utf8,
    "matchup": pl.Utf8,
    "home_team_id": pl.Int64,
    "home_team_abbreviation": pl.Utf8,
    "home_team_name": pl.Utf8,
    "home_pts": pl.Int64,
    "home_wl": pl.Utf8,
    "away_team_id": pl.Int64,
    "away_team_abbreviation": pl.Utf8,
    "away_team_name": pl.Utf8,
    "away_pts": pl.Int64,
    "away_wl": pl.Utf8,
}


def boxscore_home_team_id(raw_root: Union[str, Path], game_id: str) -> Optional[int]:
    """Official home TEAM_ID from the game's ``boxscoretraditionalv3`` capture.

    The fallback for neutral-site games, whose ``leaguegamelog`` rows carry
    ``TEAM @ OPP`` on BOTH sides so ``MATCHUP`` can't name a host. Returns
    ``None`` when the boxscore isn't captured or can't be read.

    Args:
        raw_root: Raw-store root (``hoopR-nba-stats-raw``).
        game_id: Zero-filled Utf8 game id.

    Returns:
        The home team id, or ``None`` when unresolvable.
    """
    from sportsdataverse.nba.nba_lineups import boxscore_home_away

    path = resolve_raw_path(raw_root, "boxv3", game_id)
    if path is None:
        return None
    try:
        home, _away = boxscore_home_away(json.loads(Path(path).read_text(encoding="utf-8")))
        return int(home)
    except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
        return None


def schedule_from_gamelog(raw_root: Union[str, Path], season_end: int) -> pl.DataFrame:
    """Game-level schedule pivoted from the raw ``leaguegamelog`` team rows.

    One row per game; the home side is the team whose MATCHUP contains ``vs.``.
    Neutral-site games (NBA Cup finals, Mexico City / Paris) get ``@`` on BOTH
    rows, so those fall back to the boxscore's official home designation --
    without it the home side of the game is written as all-null.
    Utf8 zero-filled ``game_id``; ``season`` is the END year. Empty frame with
    the documented schema when nothing was captured.
    """
    games: dict[str, dict[str, Any]] = {}
    for variant, headers, rows in _read_gamelog(raw_root, season_end):
        idx = {h: i for i, h in enumerate(headers)}

        def col(row: list[Any], name: str) -> Any:
            i = idx.get(name)
            return row[i] if i is not None and i < len(row) else None

        for row in rows:
            gid_raw = col(row, "GAME_ID")
            if gid_raw is None:
                continue
            gid = str(gid_raw).zfill(10)
            rec = games.setdefault(
                gid,
                {
                    "game_id": gid,
                    "season": season_end,
                    "season_type": variant,
                    "game_date": None,
                    "matchup": None,
                    "_sides": [],
                },
            )
            rec["game_date"] = rec["game_date"] or col(row, "GAME_DATE")
            pts = col(row, "PTS")
            rec["_sides"].append(
                {
                    "matchup": str(col(row, "MATCHUP") or ""),
                    "team_id": col(row, "TEAM_ID"),
                    "team_abbreviation": col(row, "TEAM_ABBREVIATION"),
                    "team_name": col(row, "TEAM_NAME"),
                    "pts": int(pts) if pts is not None else None,
                    "wl": col(row, "WL"),
                }
            )

    for gid, rec in games.items():
        sides = rec.pop("_sides")
        hosts = [s for s in sides if " vs. " in s["matchup"]]
        if len(hosts) == 1:
            home = hosts[0]
        elif len(sides) > 1:
            hid = boxscore_home_team_id(raw_root, gid)
            # ponytail: an unresolvable neutral game still keeps both teams
            # (row order) rather than nulling a whole side.
            home = next((s for s in sides if hid is not None and s["team_id"] == hid), sides[0])
        else:
            home = None
        for s in sides:
            side = "home" if s is home else "away"
            rec[f"{side}_team_id"] = s["team_id"]
            rec[f"{side}_team_abbreviation"] = s["team_abbreviation"]
            rec[f"{side}_team_name"] = s["team_name"]
            rec[f"{side}_pts"] = s["pts"]
            rec[f"{side}_wl"] = s["wl"]
        if home is not None:
            rec["matchup"] = home["matchup"] or None

    rows_out = [
        {k: g.get(k) for k in _SCHEDULE_SCHEMA}
        for g in sorted(games.values(), key=lambda g: str(g["game_id"]))
    ]
    return pl.DataFrame(rows_out, schema=_SCHEDULE_SCHEMA)


def schedule_from_league_schedule(raw_root: Union[str, Path], season_end: int) -> pl.DataFrame:
    """Game-level schedule from the raw ``scheduleleaguev2`` capture.

    Unlike ``leaguegamelog`` (captured only at ``regular-season`` / ``playoffs``),
    this payload carries **every** game type -- preseason (``001``), All-Star
    (``003``), play-in (``005``) and the NBA Cup final (``006``) included. Points
    and W/L are filled only for games played to a final, so a not-yet-played
    scheduled game doesn't land a fake 0-0.

    Args:
        raw_root: Raw-store root (``hoopR-nba-stats-raw``).
        season_end: Season **END** year (2026 = 2025-26). The payload file is
            keyed by START year, matching ``leaguegamelog``.

    Returns:
        One row per game in ``_SCHEDULE_SCHEMA``; empty frame when uncaptured.
    """
    path = Path(raw_root) / "nba_stats" / "json" / "scheduleleaguev2" / f"{season_end - 1}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return pl.DataFrame([], schema=_SCHEDULE_SCHEMA)

    rows_out: list[dict[str, Any]] = []
    for day in (payload.get("leagueSchedule") or {}).get("gameDates") or []:
        for game in day.get("games") or []:
            gid_raw = game.get("gameId")
            if gid_raw is None:
                continue
            gid = str(gid_raw).zfill(10)
            season_type = SEASON_TYPE_OF_PREFIX.get(gid[2])
            if season_type is None:
                # ponytail: type digit 9 is an arena hold (57 of them league-wide:
                # no teams, no score, never final, never captured), not a game.
                continue
            home, away = game.get("homeTeam") or {}, game.get("awayTeam") or {}
            final = game.get("gameStatus") == _GAME_STATUS_FINAL
            hp = int(home.get("score") or 0) if final else None
            ap = int(away.get("score") or 0) if final else None

            def name(team: dict[str, Any]) -> Optional[str]:
                parts = [team.get("teamCity"), team.get("teamName")]
                joined = " ".join(str(p) for p in parts if p)
                return joined or None

            rows_out.append(
                {
                    "game_id": gid,
                    "season": season_end,
                    "season_type": season_type,
                    "game_date": (str(game.get("gameDateEst") or "")[:10]) or None,
                    "matchup": (
                        f"{home.get('teamTricode')} vs. {away.get('teamTricode')}"
                        if home.get("teamTricode") and away.get("teamTricode")
                        else None
                    ),
                    "home_team_id": home.get("teamId"),
                    "home_team_abbreviation": home.get("teamTricode"),
                    "home_team_name": name(home),
                    "home_pts": hp,
                    "home_wl": None if hp is None or ap is None else ("W" if hp > ap else "L"),
                    "away_team_id": away.get("teamId"),
                    "away_team_abbreviation": away.get("teamTricode"),
                    "away_team_name": name(away),
                    "away_pts": ap,
                    "away_wl": None if hp is None or ap is None else ("L" if hp > ap else "W"),
                }
            )
    rows_out.sort(key=lambda r: str(r["game_id"]))
    return pl.DataFrame(rows_out, schema=_SCHEDULE_SCHEMA)


def season_schedule(raw_root: Union[str, Path], season_end: int) -> pl.DataFrame:
    """The season's full game universe: gamelog rows plus every other game type.

    ``leaguegamelog`` stays the metadata source wherever it has the game (it
    carries real W/L and the neutral-site home resolution); ``scheduleleaguev2``
    supplies only the game ids it never covered. Season convention is **END**
    year throughout.
    """
    gamelog = schedule_from_gamelog(raw_root, season_end)
    extra = schedule_from_league_schedule(raw_root, season_end).join(
        gamelog.select("game_id"), on="game_id", how="anti"
    )
    if extra.is_empty():
        return gamelog
    return pl.concat([gamelog, extra]).sort("game_id")


def build_season(
    raw_root: Union[str, Path],
    season_end: int,
    staging: Union[str, Path],
    cache_root: Union[str, Path],
    *,
    rebuild: bool = False,
) -> dict[str, Any]:
    """Build one season's four staged parquets from the raw store.

    Skips entirely (``status="skipped"``) when the four parquets already exist
    and ``rebuild`` is False. Per-game failures cost that game, not the season.
    """
    if not rebuild and season_done(staging, season_end):
        return {"season": season_end, "status": "skipped"}

    t0 = time.time()
    sched = season_schedule(raw_root, season_end)
    game_ids = sched["game_id"].to_list()

    processed: list[ProcessedGame] = []
    uncaptured: list[str] = []
    failed: list[str] = []
    start_year = season_end - 1
    for n, gid in enumerate(game_ids, 1):
        if resolve_raw_path(raw_root, "pbpv3", gid) is None:
            uncaptured.append(gid)
            continue
        pg = _read_game_cache(cache_root, start_year, gid)
        if pg is None:
            try:
                pg = process_game(raw_root, gid)
                write_game_cache(cache_root, start_year, pg)
            except Exception as exc:  # noqa: BLE001 - one bad game must not kill the season
                failed.append(gid)
                _log(f"  season {season_end} game {gid} FAILED: {type(exc).__name__}: {exc}")
                continue
        processed.append(pg)
        if n % 100 == 0:
            _log(f"  season {season_end}: {n}/{len(game_ids)} games ({len(failed)} failed)")

    paths = season_paths(staging, season_end)
    Path(staging).mkdir(parents=True, exist_ok=True)
    rows: dict[str, int] = {}

    sched.write_parquet(paths["schedule"])
    rows["schedule"] = sched.height

    for fam, attr in _FRAME_OF.items():
        frames = [getattr(pg, attr) for pg in processed]
        frames = [f for f in frames if isinstance(f, pl.DataFrame) and not f.is_empty()]
        if frames:
            df = pl.concat(frames, how="diagonal_relaxed")
            df = _coerce_id_dtypes(df)
            if "season" not in df.columns:
                df = df.with_columns(pl.lit(season_end, dtype=pl.Int64).alias("season"))
        else:
            df = pl.DataFrame({"game_id": pl.Series([], dtype=pl.Utf8)})
        df.write_parquet(paths[fam])
        rows[fam] = df.height

    return {
        "season": season_end,
        "status": "built",
        "games_indexed": len(game_ids),
        "games_uncaptured": len(uncaptured),
        "games_failed": len(failed),
        "games_processed": len(processed),
        "rows": rows,
        "secs": round(time.time() - t0, 1),
    }


def main(argv: Optional[list[str]] = None) -> int:
    """CLI: ``python -m nba_data_build.v3_backfill -s 1997 -e 2026``."""
    ap = argparse.ArgumentParser(
        prog="nba_data_build.v3_backfill",
        description="Program V v3 backfill (D26/D26b): raw store -> staged season parquets.",
    )
    ap.add_argument("-s", "--start-season", type=int, default=1997, help="first END-year season")
    ap.add_argument("-e", "--end-season", type=int, default=2026, help="last END-year season")
    ap.add_argument(
        "--raw-root", default=None, help="hoopR-nba-stats-raw checkout (default: sibling)"
    )
    ap.add_argument("--staging", default=None, help="staging dir (default: {repo}/v3_staging)")
    ap.add_argument(
        "--cache-dir", default=None, help="per-game cache (default: {repo}/.nba_pipeline_cache)"
    )
    ap.add_argument(
        "--rebuild", action="store_true", help="rebuild seasons whose staged parquets exist"
    )
    args = ap.parse_args(argv)

    repo = repo_root_default()
    raw_root = Path(args.raw_root) if args.raw_root else repo.parent / "hoopR-nba-stats-raw"
    staging = Path(args.staging) if args.staging else repo / "v3_staging"
    cache_root = Path(args.cache_dir) if args.cache_dir else repo / ".nba_pipeline_cache"

    if not (Path(raw_root) / "nba_stats" / "json").is_dir():
        _log(f"raw store not found at {raw_root} -- pass --raw-root")
        return 2

    _log(
        f"v3 backfill seasons {args.start_season}-{args.end_season} "
        f"raw={raw_root} staging={staging} cache={cache_root}"
    )
    failures = 0
    for season in range(args.start_season, args.end_season + 1):
        try:
            summary = build_season(raw_root, season, staging, cache_root, rebuild=args.rebuild)
        except Exception as exc:  # noqa: BLE001 - keep the range going, report at exit
            failures += 1
            _log(f"season {season} ERROR: {type(exc).__name__}: {exc}")
            continue
        _log(f"season {season}: {summary}")
    _log(f"done ({failures} season-level failures)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
