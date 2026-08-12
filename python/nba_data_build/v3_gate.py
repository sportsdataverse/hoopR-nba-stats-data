"""Section-9.3 gate: diff staged v3 seasons against legacy + the raw store.

For every requested END-year season and each of the two comparable families:

``schedule``
    Staged ``nba_schedule_{E}.parquet`` vs legacy
    ``nba_stats/schedules/parquet/schedule_{E-1}-{yy}.parquet``: game counts,
    game-id set symmetric difference, and per-game home/away score
    reconciliation. Legacy game types outside the v3 scope (preseason /
    all-star / play-in -- game-id type digit not in {2, 4}) are reported as
    *explained* exclusions, never as diffs.

``play_by_play``
    Staged ``nba_play_by_play_{E}.parquet`` vs legacy
    ``play_by_play_{E-1}-{yy}.parquet`` game-id sets, plus a final-score
    reconciliation of the staged pbp (max ``score_home``/``score_away`` per
    game) against the staged schedule.

Seasons with **no legacy counterpart** (pbp 2023+; any missing legacy file)
are validated against the raw store instead: staged games vs captured
``playbyplayv3/{E}/*.json`` files, and a min-events-per-game floor.

Exit is nonzero when any season/family verdict is DIFF (unexplained).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Optional, Union

import polars as pl

#: v3 scope: regular season (2) + playoffs (4). Other game-id type digits
#: (1=preseason, 3=all-star, 5=play-in, 6=IST) are explained exclusions.
CORE_TYPE_DIGITS = frozenset({"2", "4"})

MIN_EVENTS_PER_GAME = 1


def _ids(df: pl.DataFrame, col: str = "game_id") -> set[str]:
    if col not in df.columns:
        return set()
    return {str(v).zfill(10) for v in df[col].cast(pl.Utf8).drop_nulls().unique().to_list()}


def core_ids(ids: "set[str]") -> "set[str]":
    """Subset of ids whose game-type digit is in the v3 scope."""
    return {g for g in ids if len(g) >= 3 and g[2] in CORE_TYPE_DIGITS}


def legacy_span(season_end: int) -> str:
    return f"{season_end - 1}-{str(season_end)[-2:]}"


def legacy_schedule_path(repo_root: Union[str, Path], season_end: int) -> Path:
    return (
        Path(repo_root)
        / "nba_stats"
        / "schedules"
        / "parquet"
        / f"schedule_{legacy_span(season_end)}.parquet"
    )


def legacy_pbp_path(repo_root: Union[str, Path], season_end: int) -> Path:
    return (
        Path(repo_root)
        / "nba_stats"
        / "pbp"
        / "parquet"
        / f"play_by_play_{legacy_span(season_end)}.parquet"
    )


def legacy_schedule_scores(df: pl.DataFrame) -> pl.DataFrame:
    """``game_id, home_pts, away_pts`` from the legacy (R-produced) schedule."""
    return df.select(
        pl.col("game_id").cast(pl.Utf8).str.zfill(10),
        pl.col("home_team_score").cast(pl.Int64, strict=False).alias("home_pts"),
        pl.col("away_team_score").cast(pl.Int64, strict=False).alias("away_pts"),
    )


def staged_schedule_scores(df: pl.DataFrame) -> pl.DataFrame:
    return df.select(
        pl.col("game_id").cast(pl.Utf8).str.zfill(10),
        pl.col("home_pts").cast(pl.Int64, strict=False),
        pl.col("away_pts").cast(pl.Int64, strict=False),
    )


def pbp_final_scores(df: pl.DataFrame) -> pl.DataFrame:
    """Per-game final score from staged pbp (max running score per game)."""
    if not {"game_id", "score_home", "score_away"} <= set(df.columns):
        return pl.DataFrame(schema={"game_id": pl.Utf8, "home_pts": pl.Int64, "away_pts": pl.Int64})
    return (
        df.select(
            pl.col("game_id").cast(pl.Utf8).str.zfill(10),
            pl.col("score_home").cast(pl.Int64, strict=False),
            pl.col("score_away").cast(pl.Int64, strict=False),
        )
        .group_by("game_id")
        .agg(
            pl.col("score_home").max().alias("home_pts"),
            pl.col("score_away").max().alias("away_pts"),
        )
    )


def compare_scores(a: pl.DataFrame, b: pl.DataFrame) -> "tuple[int, int, list[str]]":
    """(games compared, mismatches, sample mismatched ids) on the id overlap.

    Only rows where both sides carry both scores are compared -- a null score
    is a coverage note, not a mismatch.
    """
    j = a.join(b, on="game_id", how="inner", suffix="_b")
    j = j.filter(
        pl.col("home_pts").is_not_null()
        & pl.col("away_pts").is_not_null()
        & pl.col("home_pts_b").is_not_null()
        & pl.col("away_pts_b").is_not_null()
    )
    bad = j.filter(
        (pl.col("home_pts") != pl.col("home_pts_b")) | (pl.col("away_pts") != pl.col("away_pts_b"))
    )
    return j.height, bad.height, bad["game_id"].head(5).to_list()


def _finding(season: int, family: str, verdict: str, detail: str) -> dict[str, Any]:
    return {"season": season, "family": family, "verdict": verdict, "detail": detail}


def gate_schedule(
    season: int,
    staged: Optional[pl.DataFrame],
    legacy: Optional[pl.DataFrame],
    raw_game_count: Optional[int],
) -> dict[str, Any]:
    """One season's schedule-family finding."""
    if staged is None:
        return _finding(season, "schedule", "MISSING_STAGED", "staged parquet absent")
    staged_set = _ids(staged)
    if legacy is None:
        detail = f"staged_games={len(staged_set)} raw_pbp_files={raw_game_count}"
        return _finding(season, "schedule", "NO_LEGACY", detail)
    legacy_all = _ids(legacy)
    legacy_core = core_ids(legacy_all)
    explained = len(legacy_all) - len(legacy_core)
    missing = sorted(legacy_core - staged_set)
    extra = sorted(staged_set - legacy_core)
    n_cmp, n_bad, bad_ids = compare_scores(
        staged_schedule_scores(staged), legacy_schedule_scores(legacy)
    )
    detail = (
        f"staged={len(staged_set)} legacy_core={len(legacy_core)} "
        f"legacy_excluded_noncore={explained} missing_in_v3={len(missing)} "
        f"extra_in_v3={len(extra)} scores_compared={n_cmp} score_mismatch={n_bad}"
    )
    if missing:
        detail += f" missing_sample={missing[:5]}"
    if extra:
        detail += f" extra_sample={extra[:5]}"
    if n_bad:
        detail += f" mismatch_sample={bad_ids}"
    verdict = "OK" if not missing and not extra and n_bad == 0 else "DIFF"
    return _finding(season, "schedule", verdict, detail)


def gate_pbp(
    season: int,
    staged_pbp: Optional[pl.DataFrame],
    staged_sched: Optional[pl.DataFrame],
    legacy_pbp: Optional[pl.DataFrame],
    raw_ids: "Optional[set[str]]",
) -> dict[str, Any]:
    """One season's pbp-family finding."""
    if staged_pbp is None:
        return _finding(season, "play_by_play", "MISSING_STAGED", "staged parquet absent")
    staged_games = _ids(staged_pbp)
    events_per_game = (
        staged_pbp.group_by(pl.col("game_id").cast(pl.Utf8)).agg(pl.len())["len"]
        if "game_id" in staged_pbp.columns and staged_pbp.height
        else pl.Series([], dtype=pl.UInt32)
    )
    min_events = int(events_per_game.min()) if len(events_per_game) else 0

    # Internal consistency: staged pbp final scores vs staged schedule scores.
    n_cmp = n_bad = 0
    bad_ids: list[str] = []
    if staged_sched is not None:
        n_cmp, n_bad, bad_ids = compare_scores(
            pbp_final_scores(staged_pbp), staged_schedule_scores(staged_sched)
        )

    if legacy_pbp is not None:
        legacy_core = core_ids(_ids(legacy_pbp))
        missing = sorted(legacy_core - staged_games)
        extra = sorted(staged_games - legacy_core)
        detail = (
            f"staged_games={len(staged_games)} legacy_core_games={len(legacy_core)} "
            f"missing_in_v3={len(missing)} extra_in_v3={len(extra)} "
            f"min_events={min_events} scores_vs_sched={n_cmp} score_mismatch={n_bad}"
        )
        if missing:
            detail += f" missing_sample={missing[:5]}"
        if extra:
            detail += f" extra_sample={extra[:5]}"
        if n_bad:
            detail += f" mismatch_sample={bad_ids}"
        ok = not missing and not extra and n_bad == 0 and min_events >= MIN_EVENTS_PER_GAME
        return _finding(season, "play_by_play", "OK" if ok else "DIFF", detail)

    # No legacy: validate against the raw store (games/season, events/game).
    raw_ids = raw_ids or set()
    uncompiled = sorted(raw_ids - staged_games)
    phantom = sorted(staged_games - raw_ids)
    detail = (
        f"staged_games={len(staged_games)} raw_captured={len(raw_ids)} "
        f"uncompiled={len(uncompiled)} phantom={len(phantom)} min_events={min_events} "
        f"scores_vs_sched={n_cmp} score_mismatch={n_bad}"
    )
    if uncompiled:
        detail += f" uncompiled_sample={uncompiled[:5]}"
    if phantom:
        detail += f" phantom_sample={phantom[:5]}"
    ok = (
        not uncompiled
        and not phantom
        and n_bad == 0
        and (min_events >= MIN_EVENTS_PER_GAME or not staged_games)
    )
    return _finding(season, "play_by_play", "NO_LEGACY_OK" if ok else "DIFF", detail)


def _read_optional(path: Path) -> Optional[pl.DataFrame]:
    return pl.read_parquet(path) if path.exists() else None


def raw_captured_ids(raw_root: Union[str, Path], season_end: int) -> "set[str]":
    d = Path(raw_root) / "nba_stats" / "json" / "playbyplayv3" / str(season_end)
    if not d.is_dir():
        return set()
    return {p.stem[:10] for p in d.glob("*.json")}


def run_gate(
    seasons: "list[int]",
    staging: Union[str, Path],
    repo_root: Union[str, Path],
    raw_root: Union[str, Path],
) -> "tuple[list[dict[str, Any]], int]":
    """Gate every season; returns (findings, exit_code)."""
    from .v3_backfill import season_paths

    findings: list[dict[str, Any]] = []
    for season in seasons:
        paths = season_paths(staging, season)
        staged_sched = _read_optional(paths["schedule"])
        staged_pbp = _read_optional(paths["play_by_play"])
        raw_ids = raw_captured_ids(raw_root, season)
        findings.append(
            gate_schedule(
                season,
                staged_sched,
                _read_optional(legacy_schedule_path(repo_root, season)),
                len(raw_ids) or None,
            )
        )
        findings.append(
            gate_pbp(
                season,
                staged_pbp,
                staged_sched,
                _read_optional(legacy_pbp_path(repo_root, season)),
                raw_ids,
            )
        )
    bad = {"DIFF", "MISSING_STAGED"}
    exit_code = 1 if any(f["verdict"] in bad for f in findings) else 0
    return findings, exit_code


def main(argv: Optional[list[str]] = None) -> int:
    """CLI: ``python -m nba_data_build.v3_gate -s 1997 -e 2026``."""
    ap = argparse.ArgumentParser(
        prog="nba_data_build.v3_gate",
        description="Program V section-9.3 gate: staged v3 vs legacy + raw store.",
    )
    ap.add_argument("-s", "--start-season", type=int, default=1997)
    ap.add_argument("-e", "--end-season", type=int, default=2026)
    ap.add_argument("--staging", default=None, help="default: {repo}/v3_staging")
    ap.add_argument("--repo-root", default=None)
    ap.add_argument("--raw-root", default=None, help="default: sibling hoopR-nba-stats-raw")
    args = ap.parse_args(argv)

    from .v3_backfill import repo_root_default

    repo = Path(args.repo_root) if args.repo_root else repo_root_default()
    staging = Path(args.staging) if args.staging else repo / "v3_staging"
    raw_root = Path(args.raw_root) if args.raw_root else repo.parent / "hoopR-nba-stats-raw"

    seasons = list(range(args.start_season, args.end_season + 1))
    findings, exit_code = run_gate(seasons, staging, repo, raw_root)
    print(f"{'season':>6} {'family':<14} {'verdict':<14} detail")
    for f in findings:
        print(f"{f['season']:>6} {f['family']:<14} {f['verdict']:<14} {f['detail']}")
    print(f"gate: {'FAIL' if exit_code else 'PASS'} ({len(findings)} findings)")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
