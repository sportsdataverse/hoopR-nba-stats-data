"""``python -m nba_data_build.reshape``: build released datasets from the raw store, optionally publish.

For each requested ``(dataset, season)`` this builds the frame, writes the three
release formats (parquet + rds + csv) under ``{out}/{release_tag}/``, and — only
when ``--publish`` is passed and ``--dry-run`` is not — uploads them to the
``nba_stats_*`` GitHub release tags, creating any tag that does not exist yet.

Build dispatch
--------------
Most datasets go through :func:`~nba_data_build.reshape.build.build` (the resultSets
path). Three v3-nested datasets need their dedicated builders instead, and the
CLI is where that routing lives:

* ``pbp`` -> :func:`~nba_data_build.reshape.build.build_pbp` (rows under ``game.actions``)
* ``player_boxscores`` / ``team_boxscores`` -> :func:`~nba_data_build.reshape.build.build_boxscores`
* ``shots`` -> :func:`~nba_data_build.reshape.build.build_shots`, *derived* from that
  season's pbp frame — so pbp is built once per season and reused, never twice.

Season floor
------------
A dataset whose source endpoint has no data before some season (``season_floor``)
produces no artifact for pre-floor seasons: the CLI skips it before building
rather than shipping an empty release (only ``lineups`` has a floor above 1996).

Publish is controller-gated
---------------------------
The default (no flags) and ``--dry-run`` both stop after writing locally under
``--out``: nothing is uploaded. ``--dry-run`` wins if both it and ``--publish``
are passed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import polars as pl

from nba_data_build.publish import upload_artifacts

from . import build as _build
from .datasets import BY_KEY, DATASETS, Dataset
from .io import write_release_formats

_REPO = "sportsdataverse/sportsdataverse-data"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="nba_data_build.reshape")
    ap.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        required=True,
        help="season START years to build, e.g. 2013 (NBA season 2013 = 2013-14)",
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
) -> pl.DataFrame:
    """Build one dataset for one season, routing v3-nested datasets to their builders.

    ``_pbp`` lets the caller pass an already-built play-by-play frame so ``shots``
    (derived from pbp) and ``pbp`` itself share one bind per season.
    """
    if dataset.key == "pbp":
        return _pbp if _pbp is not None else _build.build_pbp(root, season)
    if dataset.key == "shots":
        pbp = _pbp if _pbp is not None else _build.build_pbp(root, season)
        return _build.build_shots(pbp)
    if dataset.key == "player_boxscores":
        return _build.build_boxscores(root, season, team_level=False)
    if dataset.key == "team_boxscores":
        return _build.build_boxscores(root, season, team_level=True)
    return _build.build(root, dataset, season)


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root)
    out = Path(args.out)
    seasons = sorted(set(args.seasons))
    datasets = _resolve_datasets(args.datasets)
    stamp = datetime.now(timezone.utc)

    # pbp and shots share one bind per season; build it lazily, once, when needed.
    want_keys = {d.key for d in datasets}
    built_tags: set[str] = set()

    for season in seasons:
        pbp: Optional[pl.DataFrame] = None
        if {"pbp", "shots"} & want_keys:
            pbp = _build.build_pbp(root, season)
        for dataset in datasets:
            # Pre-floor seasons have no source data: skip rather than ship an
            # empty release (only lineups has a floor above the 1996 full history).
            if dataset.season_floor is not None and season < dataset.season_floor:
                print(
                    f"skip {dataset.key} {season}: below season_floor "
                    f"{dataset.season_floor}"
                )
                continue
            df = build_dataset(root, dataset, season, _pbp=pbp)
            if df.is_empty():
                print(f"skip {dataset.key} {season}: no rows")
                continue
            paths = write_release_formats(
                df,
                out / dataset.release_tag,
                f"{dataset.stem}_{season}",
                nba_type=dataset.nba_type,
                timestamp=stamp,
            )
            built_tags.add(dataset.release_tag)
            print(
                f"built {dataset.key} {season}: {df.height} rows -> {paths['parquet'].name}"
            )

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
                seasons=seasons,
                exts=("parquet", "rds", "csv"),
                dry_run=args.dry_run,
            )
            print(f"publish {tag}: {result}")
    else:
        print("no --publish/--dry-run: artifacts written locally, nothing uploaded")
    return 0
