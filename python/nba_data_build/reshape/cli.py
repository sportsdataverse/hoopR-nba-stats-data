"""``python -m nba_data_build.reshape``: build released datasets from the raw store, optionally publish.

For each requested ``(dataset, season)`` this builds the frame, writes the three
release formats (parquet + rds + csv) under ``{out}/{release_tag}/``, and — only
when ``--publish`` is passed and ``--dry-run`` is not — uploads them to the
``nba_stats_*`` GitHub release tags, creating any tag that does not exist yet.

Build dispatch
--------------
Most datasets go through :func:`~nba_data_build.reshape.build.build` (the resultSets
path). The v3-nested datasets need their dedicated builders instead, and the
CLI is where that routing lives:

* ``player_boxscores`` / ``team_boxscores`` -> :func:`~nba_data_build.reshape.build.build_boxscores`
* ``game_matchups`` -> :func:`~nba_data_build.reshape.build.build_matchups` (players
  nested inside players)
* ``shots`` -> :func:`~nba_data_build.reshape.build.build_shots`, *derived* from that
  season's play-by-play frame (:func:`~nba_data_build.reshape.build.build_pbp`, rows
  under ``game.actions``), built in memory only. The ``pbp`` dataset itself was
  retired 2026-09-30 (v3 ``nba_play_by_play`` replaces it), so nothing publishes it.
* ``rolling_windows`` -> :func:`~nba_data_build.reshape.build.build_rolling_windows`,
  *derived* the same way, plus every earlier committed ``shots`` season under
  ``--base`` and the committed schedule master (game dates).
* ``metric_curves`` -> :func:`~nba_data_build.reshape.build.build_metric_curves`,
  *derived* from that season's ``shots`` -- the frame this run just built when
  ``shots`` is in the run (the daily processor), else the committed
  ``{--base}/shots/parquet/shots_{season}.parquet`` (a standalone backfill).

Season floor
------------
A dataset whose source endpoint has no data before some season (``season_floor``)
produces no artifact for pre-floor seasons: the CLI skips it before building
rather than shipping an empty release (``lineups`` and ``game_matchups`` have floors
above the 1997 full history).

Publish is controller-gated
---------------------------
The default (no flags) and ``--dry-run`` both stop after writing locally under
``--out``: nothing is uploaded. ``--dry-run`` wins if both it and ``--publish``
are passed.

Everything is keyed by the season's END year
--------------------------------------------
``--seasons`` takes the END year, which is also the raw-store directory (both
halves of the store are END-keyed since the 2026-09-30 re-key) and the published
year: the 1996-97 season is ``--seasons 1997`` and ships as
``coaches_1997.parquet`` with ``season = 1997``. Filename and column carry the
same year; sdv-db's ingest refuses a frame whose ``season`` disagrees, and
sportsdataverse-py's ``load_nba_stats_*`` fetch these names directly.

hoopR is NOT a consumer of these tags — its ``load_nba_*`` read the ESPN-sourced
``espn_nba_*`` releases, so the rename does not touch the R side. wehoop DOES
read ``wnba_stats_*``, so the equivalent WNBA change would not be free.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import polars as pl

from nba_data_build.publish import upload_artifacts

from . import build as _build
from .datasets import BY_KEY, DATASETS, RELEASE_NOTES, Dataset
from .io import write_release_formats
from .raw import _is_url

_REPO = "sportsdataverse/sportsdataverse-data"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="nba_data_build.reshape")
    ap.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        required=True,
        help="season END years to build, e.g. 2014 (NBA season 2014 = 2013-14)",
    )
    ap.add_argument(
        "--datasets",
        nargs="+",
        default=None,
        metavar="KEY",
        help=f"subset of dataset keys to build (default: all). Choices: {', '.join(BY_KEY)}",
    )
    ap.add_argument(
        "--root",
        default="nba_stats/json",
        help="raw-store json base (the dir holding {endpoint}/{season}/), local path "
        "to the hoopR-nba-stats-raw store or a raw.githubusercontent URL; default "
        "matches the sibling -raw checkout's nba_stats/json base",
    )
    ap.add_argument("--out", default="build_out", help="artifact output directory")
    ap.add_argument(
        "--base",
        default="nba_stats",
        help="committed tree (the dir holding shots/parquet/) that metric_curves reads the "
        "season's shots from when shots is not built in the same run; default = this "
        "repo's tree relative to the cwd the drivers cd into",
    )
    ap.add_argument("--repo", default=_REPO, help="release repo for --publish")
    ap.add_argument(
        "--publish",
        action="store_true",
        help="upload built artifacts to their release tags (creating missing tags)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="plan the publish without uploading; wins over --publish if both are set",
    )
    return ap


def _resolve_datasets(keys: Optional[list[str]]) -> list[Dataset]:
    """Datasets to build, in registry order. Raises on an unknown key."""
    if keys is None:
        return list(DATASETS)
    unknown = [k for k in keys if k not in BY_KEY]
    if unknown:
        raise SystemExit(f"unknown dataset key(s): {', '.join(unknown)}")
    order = {d.key: i for i, d in enumerate(DATASETS)}
    return sorted((BY_KEY[k] for k in dict.fromkeys(keys)), key=lambda d: order[d.key])


def build_dataset(
    root: str | Path,
    dataset: Dataset,
    season: int,
    *,
    _pbp: Optional[pl.DataFrame] = None,
    _shots: Optional[pl.DataFrame] = None,
    base: str | Path = "nba_stats",
) -> pl.DataFrame:
    """Build one dataset for one season, routing v3-nested datasets to their builders.

    ``_pbp`` lets the caller pass an already-built play-by-play frame for ``shots``
    (derived from pbp) so the season's pbp is bound once; ``_shots`` does the same
    for ``rolling_windows`` and ``metric_curves`` (derived from shots), which
    otherwise read the committed tree under ``base``.
    """
    if dataset.key == "shots":
        pbp = _pbp if _pbp is not None else _build.build_pbp(root, season)
        return _build.build_shots(pbp)
    if dataset.key == "rolling_windows":
        return _build.build_rolling_windows(base, season, _shots)
    if dataset.key == "metric_curves":
        shots = _shots if _shots is not None else _build.committed_shots(base, season)
        return _build.build_metric_curves(shots)
    if dataset.key == "player_boxscores":
        return _build.build_boxscores(root, season, team_level=False)
    if dataset.key == "team_boxscores":
        return _build.build_boxscores(root, season, team_level=True)
    if dataset.key == "game_matchups":
        return _build.build_matchups(root, season)
    return _build.build(root, dataset, season)


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    # Keep a URL root a STRING. Path("https://host/x") collapses the double slash
    # (and flips separators on Windows) to "https:/host/x", which raw._is_url no
    # longer recognises -- the build then silently falls through to filesystem
    # reads against a path that cannot exist.
    root: str | Path = args.root if _is_url(args.root) else Path(args.root)
    out = Path(args.out)
    seasons = sorted(set(args.seasons))
    datasets = _resolve_datasets(args.datasets)
    stamp = datetime.now(timezone.utc)

    # shots derives from the season's pbp frame; build it once, only when needed.
    want_keys = {d.key for d in datasets}
    built_tags: set[str] = set()

    for season in seasons:
        pbp: Optional[pl.DataFrame] = None
        if "shots" in want_keys:
            pbp = _build.build_pbp(root, season)
        # rolling_windows / metric_curves derive from THIS run's shots (registry order
        # builds shots first), never from yesterday's committed file when both are in
        # the run.
        shots: Optional[pl.DataFrame] = None
        for dataset in datasets:
            # Pre-floor seasons have no source data: skip rather than ship an
            # empty release (see Dataset.season_floor).
            if dataset.season_floor is not None and season < dataset.season_floor:
                print(f"skip {dataset.key} {season}: below season_floor {dataset.season_floor}")
                continue
            df = build_dataset(root, dataset, season, _pbp=pbp, _shots=shots, base=args.base)
            if dataset.key == "shots":
                shots = df
            if df.is_empty():
                print(f"skip {dataset.key} {season}: no rows")
                continue
            # Every builder already stamps `season` with this END year, so the
            # filename and the column agree without any conversion here.
            paths = write_release_formats(
                df,
                out / dataset.release_tag,
                f"{dataset.stem}_{season}",
                nba_type=dataset.nba_type,
                timestamp=stamp,
            )
            built_tags.add(dataset.release_tag)
            print(f"built {dataset.key} {season}: {df.height} rows -> {paths['parquet'].name}")

    failed_uploads: list[tuple[str, list]] = []
    if args.publish or args.dry_run:
        for tag in sorted(built_tags):
            # All three formats ship to the tag: hoopR::load_nba_*() reads the
            # .rds and the release is the only channel that carries rds/csv (the
            # repo commits none of them). publish.py defaults to parquet-only for
            # the v3/modeling tags, so the reshaper opts in explicitly here.
            result = upload_artifacts(
                out / tag,
                tag,
                args.repo,
                # plan_uploads scopes by matching `_{season}.{ext}` against the
                # filenames on disk, which carry the same END year as --seasons.
                seasons=seasons,
                exts=("parquet", "rds", "csv"),
                notes=RELEASE_NOTES.get(tag),
                dry_run=args.dry_run,
            )
            print(f"publish {tag}: {result}")
            # upload_artifacts is best-effort per file, so a parquet can land while
            # the .rds/.csv beside it fail. Reporting success there would leave the
            # tag half-populated while every downstream freshness check reads it as
            # complete -- consumers of the missing formats then silently see the
            # PREVIOUS season's asset. Surface it as a failed run.
            if result.get("failed"):
                failed_uploads.append((tag, list(result["failed"])))
    else:
        print("no --publish/--dry-run: artifacts written locally, nothing uploaded")

    if failed_uploads:
        for tag, assets in failed_uploads:
            print(
                f"ERROR: {tag} is INCOMPLETE -- {len(assets)} asset(s) failed to upload: "
                f"{', '.join(assets)}",
                file=sys.stderr,
            )
        return 1
    return 0
