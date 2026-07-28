"""Publish built parquet to sportsdataverse-data GitHub releases (gh CLI)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, Optional

_GH_TIMEOUT = 600
_SEASON_RE = re.compile(r"_(\d{4})\.parquet$")

# FIX 3: module-level type aliases for injectable gh-runner and exists-check callables.
Runner = Callable[[list[str]], str]
ExistsCheck = Callable[[str, str], bool]


def _gh_runner(args: list[str]) -> str:
    """Run `gh <args>`, returning stdout. Raises on non-zero."""
    return subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True, timeout=_GH_TIMEOUT
    ).stdout


def _gh_release_exists(tag: str, repo: str) -> bool:
    try:
        subprocess.run(
            ["gh", "release", "view", tag, "--repo", repo],
            check=True,
            capture_output=True,
            timeout=_GH_TIMEOUT,
        )
        return True
    except subprocess.CalledProcessError:
        # FIX 2: subprocess.TimeoutExpired is intentionally NOT caught here — a spurious
        # False would trigger a `gh release create` that then fails because the release
        # already exists.
        return False


def plan_uploads(
    artifacts_dir: Path,
    seasons: Optional[Iterable[int]] = None,
    *,
    pattern: str = "*.parquet",
) -> list[Path]:
    """Return the files under *artifacts_dir* matching *pattern* (sorted).

    ``seasons``, when given, scopes this to only files ending in
    ``_{season}.parquet`` for one of the given seasons -- otherwise every
    prior season's files sitting in the same directory get globbed in too,
    which turns a single-season publish call into an ever-growing re-upload
    of the whole backfill-to-date (O(n^2) across a multi-season backfill).
    Season scoping only makes sense for the default parquet pattern; a
    non-parquet *pattern* (e.g. a model-card ``*.json``) is returned unscoped.
    """
    files = sorted(Path(artifacts_dir).glob(pattern))
    if seasons is None or pattern != "*.parquet":
        return files
    suffixes = tuple(f"_{s}.parquet" for s in seasons)
    return [f for f in files if f.name.endswith(suffixes)]


def published_seasons(
    tag: str, repo: str, *, runner: Optional[Runner] = None
) -> set[int]:
    """Season end-years already on the release, parsed from `_{season}.parquet` asset names.

    Returns an empty set if the release does not exist.
    """
    # FIX 4: drop needless lambda — _gh_runner already matches the Runner signature.
    run = runner or _gh_runner
    try:
        out = run(
            [
                "release",
                "view",
                tag,
                "--repo",
                repo,
                "--json",
                "assets",
                "--jq",
                ".assets[].name",
            ]
        )
    except subprocess.CalledProcessError as exc:
        # A missing release is expected on the first run -> empty set. Any OTHER gh
        # failure (auth, permission, rate limit) must surface, not masquerade as
        # "nothing published" (which would trigger a full, multi-hour recompile).
        stderr = (exc.stderr or "").lower()
        if "not found" in stderr:
            return set()
        raise
    return {
        int(m.group(1))
        for line in (out or "").splitlines()
        if (m := _SEASON_RE.search(line))
    }


def upload_artifacts(
    artifacts_dir: Path,
    tag: str,
    repo: str,
    *,
    seasons: Optional[Iterable[int]] = None,
    pattern: str = "*.parquet",
    notes: Optional[str] = None,
    dry_run: bool = False,
    runner: Optional[Runner] = None,
    exists_check: Optional[ExistsCheck] = None,
) -> dict[str, object]:
    """Upload each parquet under *artifacts_dir* to release *tag* on *repo* (creating it if needed).

    ``seasons`` scopes the upload set (see :func:`plan_uploads`) -- pass the
    seasons this invocation actually built, not the whole directory. Each
    file uploads best-effort: one failed ``gh release upload`` is logged and
    skipped rather than aborting every file still queued behind it.

    ``pattern`` selects a non-default asset set (e.g. a model-card
    ``"*_card.json"`` sidecar); season scoping applies only to the default
    parquet pattern. ``notes`` overrides the release body used when the
    release has to be created (existing releases are never edited).

    ``runner`` (default: real `gh` subprocess) and ``exists_check`` are injectable for tests.

    Returns:
        dict with keys:
            ``uploaded``: int count of files uploaded (0 if *dry_run* is True).
            ``failed``: list of asset filenames whose upload raised.
            ``files``: list of asset filenames that were (or would be) uploaded.
    """
    # FIX 4: drop needless lambda — _gh_runner already matches the Runner signature.
    run = runner or _gh_runner
    exists = exists_check or _gh_release_exists
    files = plan_uploads(artifacts_dir, seasons, pattern=pattern)
    if dry_run:
        return {"uploaded": 0, "failed": [], "files": [f.name for f in files]}
    if not exists(tag, repo):
        run(
            [
                "release",
                "create",
                tag,
                "--repo",
                repo,
                "--title",
                tag,
                "--notes",
                notes or f"{tag} datasets (NBA model zoo)",
            ]
        )
    uploaded: list[str] = []
    failed: list[str] = []
    for f in files:
        try:
            run(["release", "upload", tag, str(f), "--repo", repo, "--clobber"])
            uploaded.append(f.name)
        except subprocess.CalledProcessError as exc:
            print(f"WARNING: upload failed for {f.name}: {exc}", file=sys.stderr)
            failed.append(f.name)
    return {
        "uploaded": len(uploaded),
        "failed": failed,
        "files": [f.name for f in files],
    }
