"""``pipeline`` CLI verb: scrape -> process -> rollup -> flags, with a mandatory dry-run.

Drives Tasks 4-9 end to end for one or more seasons:

1. :func:`_discover_finished` -- which games are finished for *season* (default: the
   sdv-py NBA-Stats-native schedule loader; module-level so tests/CI inject a
   network-free fake).
2. :func:`~nba_data_build.scrape.orchestrate.scrape_finished_games` -- verbatim raw
   capture (resumable: already-captured games are skipped unless ``--rescrape``).
3. :func:`~nba_data_build.process.datasets.rollup_season` -- from-raw compile into the
   three committed v3 parquet datasets (guarded by ``PIPELINE_VERSION>=3``).
4. :func:`~nba_data_build.process.availability.compute_flags` -- v3 availability flags,
   upserted into the committed ``nba_stats_schedule_master.parquet`` plus a per-season
   v3 discovery/flags snapshot.

**Publish is controller-gated.** ``main()`` only ever calls :func:`_publish` when
``--publish`` is passed *and* ``--dry-run`` is not (dry-run always wins if both are
somehow set). The default (no flags at all) and ``--dry-run`` both stop after step 4:
everything above writes locally under ``--root``; nothing is committed, pushed, or
uploaded.

Schedule-master grounding
-------------------------
The repo already ships a real, committed ``{root}/nba_stats/nba_stats_schedule_master.parquet``
(48 ESPN-shaped columns, ``season`` as ``"YYYY-YY"``, ``game_id`` as ``Utf8``) written by the
R-side producer. Its ``game_status``/score columns are stale placeholders (schedule-fetch-time
snapshots, never refreshed post-game) -- **not** a reliable "is this game finished" signal for
the v3 pipeline. :func:`_discover_finished`'s default implementation therefore sources
discovery from sdv-py's NBA-Stats-native schedule loader (real ``game_status`` semantics:
1=scheduled / 2=live / 3=final), not this file. The master file is only a **write target**:
:func:`_write_schedule` upserts the five new v3 flag columns onto it by ``game_id``, leaving
every other column and every other season's rows untouched.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, Union

import polars as pl

from .cache_guard import assert_pipeline_version
from .process.availability import compute_flags
from .process.datasets import rollup_season
from .scrape.client import V3Client
from .scrape.orchestrate import scrape_finished_games

logger = logging.getLogger(__name__)

_DEFAULT_REPO = "sportsdataverse/sportsdataverse-data"
_FLAG_COLS = ("PBP_V3", "BOX_V3", "BOX_PERIODS", "POSS", "LINEUP")
_MASTER_SCHEDULE_NAME = "nba_stats_schedule_master.parquet"
_FINISHED_STATUS = 3
_GIT_TIMEOUT = 600

Runner = Callable[[list[str]], str]


def build_pipeline_parser() -> argparse.ArgumentParser:
    """Build the ``pipeline`` verb's argument parser.

    Returns:
        An :class:`argparse.ArgumentParser` with ``--seasons`` / ``--root`` /
        ``--rescrape`` / ``--dry-run`` / ``--publish`` / ``--target`` / ``--cache-dir``
        / ``--repo``.
    """
    ap = argparse.ArgumentParser(
        prog="nba_data_build pipeline",
        description=(
            "NBA-Stats v3 pipeline: scrape -> process -> rollup -> flags. "
            "Requires the Task 5 one-game proxy probe (OD1) to have passed once, from a "
            "residential IP or with proxies configured, before fanning out to real seasons. "
            "Default (no --publish) NEVER commits, pushes, or uploads -- everything writes "
            "locally under --root."
        ),
    )
    ap.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        required=True,
        help="season start-years to run, e.g. 2023 for the 2023-24 season",
    )
    ap.add_argument(
        "--root",
        default=".",
        help="repo data root -- parent of nba_stats/ (e.g. '..' when run from python/)",
    )
    ap.add_argument(
        "--rescrape",
        action="store_true",
        help="re-fetch and overwrite already-captured raw games instead of skipping them",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "default-safe: scrape -> process -> rollup -> flags, all written locally; "
            "never commits, pushes, or uploads. Wins over --publish if both are passed."
        ),
    )
    ap.add_argument(
        "--publish",
        action="store_true",
        help=(
            "CONTROLLER-APPROVED ONLY: commit nba_stats/* with the preserved subject "
            "'NBA Stats Update (Start: {season} End: {season})' (and, with "
            "--target release, additionally mirror rollups to GitHub release tags). "
            "Never runs when --dry-run is also set."
        ),
    )
    ap.add_argument(
        "--target",
        choices=("commit", "release"),
        default="commit",
        help=(
            "publish layout (OD2, unresolved -- pick per run): 'commit' (default, safer) "
            "commits nba_stats/* straight to git; 'release' does the same commit AND "
            "additionally mirrors the per-season pbpv3/possessions/lineups rollups to "
            "dedicated GitHub release tags (nba_stats_pbpv3 / nba_stats_possessions_v3 / "
            "nba_stats_lineups_v3 -- distinct from the modeling build's nba_stats_rapm / "
            "nba_stats_possessions tags)."
        ),
    )
    ap.add_argument(
        "--cache-dir",
        default=None,
        help="per-game resumability cache root (default: {root}/.nba_pipeline_cache)",
    )
    ap.add_argument("--repo", default=_DEFAULT_REPO, help="release repo for --target release")
    return ap


def _discover_finished(season: int, root: Union[str, Path]) -> list[dict[str, Any]]:
    """Default finished-game discovery: sdv-py's NBA-Stats-native schedule loader.

    Seam (mirrors the Task 7 quarter-box seam pattern): module-level so tests/CI
    monkeypatch this wholesale with a network-free fake. See the module docstring for
    why this does NOT read the committed ``nba_stats_schedule_master.parquet``.

    Args:
        season: Season start-year (e.g. 2023 for 2023-24).
        root: Dataset root (unused by the default implementation, kept in the signature
            so a root-aware override -- e.g. one that also reads a local cache -- is a
            drop-in swap).

    Returns:
        A list of row dicts (``game_id`` / ``game_status`` / ``home_team_id`` / ...),
        filtered to ``game_status == 3`` (final). Schedule rows carry no per-game period
        count, so every row implicitly relies on :func:`~nba_data_build.scrape.orchestrate.scrape_finished_games`'s
        ``n_periods`` default of 4 (regulation) -- OT games need a later ``--rescrape``
        once a period-count source is available (tracked as a known gap, see README).
    """
    from sportsdataverse.nba.nba_loaders import load_nba_stats_schedules

    sched = load_nba_stats_schedules([season])
    finished = sched.filter(pl.col("game_status") == _FINISHED_STATUS)
    return finished.to_dicts()


def _make_client() -> V3Client:
    """Default client factory: the real proxy-rotated, rate-limited :class:`V3Client`.

    Reads proxy credentials (``PROXY_ENDPOINT``/``PROXY_KEY``/``PROXY_PKG``) at call
    time via :func:`~nba_data_build.scrape.proxy.load_proxies` -- never at import time,
    never logged/cached in cleartext. Module-level so tests/CI monkeypatch this wholesale.
    """
    from .scrape.proxy import RoundRobin, load_proxies

    return V3Client(proxies=RoundRobin(load_proxies()))


def _finished_game_ids(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Apply the same finished/non-TBD filter as ``scrape_finished_games`` to *rows*.

    Defensive: even though the default :func:`_discover_finished` already pre-filters,
    a caller-supplied override isn't guaranteed to -- rolling up a live or TBD game
    would hit ``process_game``'s ``FileNotFoundError`` (its raw capture was never
    written), so the same filter is applied again here before building the rollup's
    ``game_ids`` list.
    """
    out = []
    for row in rows:
        if int(row.get("game_status", _FINISHED_STATUS)) != _FINISHED_STATUS:
            continue
        if int(row.get("home_team_id", 1)) == 0:
            continue
        out.append(str(row["game_id"]))
    return out


def _season_snapshot_path(root: Union[str, Path], season: int) -> Path:
    """Per-season v3 discovery+flags snapshot path (does NOT touch the R-authored ``schedules/`` dir)."""
    return Path(root) / "nba_stats" / "schedule_v3" / "parquet" / f"nba_schedule_v3_{season}.parquet"


def _upsert_master_flags(existing: Optional[pl.DataFrame], flagged_season: pl.DataFrame) -> pl.DataFrame:
    """Merge one season's freshly-computed v3 flags onto the schedule master, preserving history.

    Only rows whose ``game_id`` appears in *flagged_season* get their flag columns
    updated; every other row (other seasons, or games this run didn't discover) keeps
    whatever value *existing* already had (``null`` if never computed).

    A game_id this run discovered that the master didn't have any row for at all yet
    (e.g. a season the R-side schedule producer hasn't captured, or a NBA-Stats-loader
    id the ESPN-sourced master never carried) is appended as a new row (via
    ``diagonal_relaxed``, since ``flagged_season``'s thin discover-row schema won't
    have the master's full ~48 ESPN-shaped columns) rather than silently dropped.

    Args:
        existing: The current ``nba_stats_schedule_master.parquet`` contents, or
            ``None`` if the file doesn't exist yet.
        flagged_season: This season's schedule slice with the five v3 flag columns
            attached (output of :func:`~nba_data_build.process.availability.compute_flags`).

    Returns:
        The merged frame to write back to the master path.
    """
    flag_cols = [c for c in _FLAG_COLS if c in flagged_season.columns]
    flagged_season = flagged_season.with_columns(pl.col("game_id").cast(pl.Utf8))
    if existing is None:
        return flagged_season

    existing = existing.with_columns(pl.col("game_id").cast(pl.Utf8))
    existing_ids = set(existing["game_id"].to_list())
    new_slice = flagged_season.select(["game_id", *flag_cols])

    # Rows the master already has: left join updates just the flag columns, in place.
    joined = existing.join(new_slice, on="game_id", how="left", suffix="_v3new")
    exprs = []
    for c in flag_cols:
        new_c = f"{c}_v3new"
        if c in existing.columns:
            exprs.append(pl.coalesce([pl.col(new_c), pl.col(c)]).alias(c))
        else:
            exprs.append(pl.col(new_c).alias(c))
    joined = joined.with_columns(exprs).drop([f"{c}_v3new" for c in flag_cols if f"{c}_v3new" in joined.columns])

    # Rows this run discovered that the master never had at all -- append, don't drop.
    brand_new = flagged_season.filter(~pl.col("game_id").is_in(list(existing_ids)))
    if brand_new.height:
        joined = pl.concat([joined, brand_new], how="diagonal_relaxed")
    return joined


def _write_schedule(root: Union[str, Path], season: int, flagged: pl.DataFrame) -> tuple[Path, Path]:
    """Write the per-season v3 snapshot and upsert flags into the committed schedule master.

    Args:
        root: Dataset root.
        season: Season start-year.
        flagged: Output of :func:`~nba_data_build.process.availability.compute_flags`
            for this season's discovered rows.

    Returns:
        ``(season_snapshot_path, master_path)``.
    """
    root = Path(root)
    season_path = _season_snapshot_path(root, season)
    season_path.parent.mkdir(parents=True, exist_ok=True)
    flagged.write_parquet(season_path)

    master_path = root / "nba_stats" / _MASTER_SCHEDULE_NAME
    existing = pl.read_parquet(master_path) if master_path.exists() else None
    merged = _upsert_master_flags(existing, flagged)
    master_path.parent.mkdir(parents=True, exist_ok=True)
    merged.write_parquet(master_path)
    return season_path, master_path


def _git_runner(args: list[str], *, cwd: Path) -> str:
    """Run ``git <args>`` in *cwd*, returning stdout. Raises on non-zero exit."""
    return subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True, timeout=_GIT_TIMEOUT
    ).stdout


def _publish(
    root: Union[str, Path],
    seasons: Sequence[int],
    *,
    target: str = "commit",
    repo: str = _DEFAULT_REPO,
    runner: Optional[Runner] = None,
    git_runner: Optional[Runner] = None,
) -> dict[str, Any]:
    """Stage + commit ``nba_stats/*`` (and, for ``target="release"``, mirror to release tags).

    **CONTROLLER-GATED**: only ever invoked from :func:`main` when ``args.publish`` is
    set and ``args.dry_run`` is not -- never call this directly against a real remote
    without that same gate. Stages an explicit path (``nba_stats``), never a blind
    ``git add -A`` / ``git commit -a``.

    Args:
        root: Repo root (parent of ``nba_stats/``).
        seasons: Season start-years processed this run -- used to build the preserved
            commit subject ``NBA Stats Update (Start: {min} End: {max})``.
        target: ``"commit"`` (default) or ``"release"`` (OD2 Option B: additionally
            mirrors the per-season rollups to dedicated GitHub release tags).
        repo: Release repo for ``target="release"``.
        runner: Injectable ``gh`` command runner (see
            :mod:`~nba_data_build.publish`), for tests.
        git_runner: Injectable ``git`` command runner, for tests.

    Returns:
        A dict describing what happened: ``{"committed": bool, ...}``. ``committed`` is
        ``False`` (no-op) when there is nothing staged under ``nba_stats/``.
    """
    root = Path(root)
    git = git_runner or (lambda args: _git_runner(args, cwd=root))

    status = git(["status", "--porcelain", "--", "nba_stats"])
    if not status.strip():
        return {"committed": False, "reason": "no changes under nba_stats/", "target": target}

    subject = f"NBA Stats Update (Start: {min(seasons)} End: {max(seasons)})"
    git(["add", "nba_stats"])
    git(["commit", "-m", subject])
    result: dict[str, Any] = {"committed": True, "subject": subject, "target": target}

    if target == "release":
        from .publish import upload_artifacts

        mirrors = {
            "nba_stats_pbpv3": root / "nba_stats" / "pbpv3" / "parquet",
            "nba_stats_possessions_v3": root / "nba_stats" / "possessions" / "parquet",
            "nba_stats_lineups_v3": root / "nba_stats" / "lineups" / "parquet",
        }
        result["release_mirror"] = {
            tag: upload_artifacts(d, tag, repo, runner=runner) for tag, d in mirrors.items() if d.exists()
        }
    return result


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point for ``python -m nba_data_build pipeline``.

    Args:
        argv: Argument list (excluding the program name), or ``None`` to use
            ``sys.argv[1:]`` via argparse's default.

    Returns:
        Process exit code (always ``0`` on a completed run; ``assert_pipeline_version``
        raises rather than returning non-zero on a stale sdv-py pin).

    Example:
        Quick start::

            from nba_data_build import pipeline_cli
            rc = pipeline_cli.main(["--seasons", "2023", "--root", "..", "--dry-run"])
    """
    args = build_pipeline_parser().parse_args(argv)
    assert_pipeline_version()

    root = Path(args.root)
    cache_root = Path(args.cache_dir) if args.cache_dir else root / ".nba_pipeline_cache"
    client: Optional[V3Client] = None

    for season in sorted(args.seasons):
        rows = _discover_finished(season, root)
        game_ids = _finished_game_ids(rows)

        if rows:
            if client is None:
                client = _make_client()
            scrape_finished_games(client, root, rows, rescrape=args.rescrape)

        rollup_paths = rollup_season(root, season, game_ids, cache_root=cache_root) if game_ids else {}

        schedule = pl.DataFrame(rows) if rows else pl.DataFrame(schema={"game_id": pl.Utf8})
        flagged = compute_flags(root, schedule)
        season_path, master_path = _write_schedule(root, season, flagged)

        logger.info(
            "pipeline: season %s -> %d finished game(s); rollup=%s; schedule=%s; master=%s",
            season,
            len(game_ids),
            sorted(rollup_paths),
            season_path,
            master_path,
        )
        print(
            f"pipeline: season {season} -> {len(game_ids)} finished game(s); "
            f"rollup={sorted(rollup_paths)}; schedule={season_path.name}; master updated"
        )

    if args.publish and not args.dry_run:
        result = _publish(root, args.seasons, target=args.target, repo=args.repo)
        print(f"pipeline: publish -> {result}")
    else:
        print("pipeline: dry-run / no --publish -- nothing committed, nothing pushed, nothing uploaded")

    return 0
