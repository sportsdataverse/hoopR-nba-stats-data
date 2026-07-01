"""Publish built parquet to sportsdataverse-data GitHub releases (gh CLI)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable, Optional

_GH_TIMEOUT = 600
_SEASON_RE = re.compile(r"_(\d{4})\.parquet$")


def _gh_runner(args: list[str]) -> str:
    """Run `gh <args>`, returning stdout. Raises on non-zero."""
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True,
                          timeout=_GH_TIMEOUT).stdout


def _gh_release_exists(tag: str, repo: str) -> bool:
    try:
        subprocess.run(["gh", "release", "view", tag, "--repo", repo],
                       check=True, capture_output=True, timeout=_GH_TIMEOUT)
        return True
    except subprocess.CalledProcessError:
        return False


def plan_uploads(artifacts_dir: Path) -> list[Path]:
    """Return the *.parquet files under *artifacts_dir* (sorted)."""
    return sorted(Path(artifacts_dir).glob("*.parquet"))


def published_seasons(tag: str, repo: str, *, runner: Optional[Callable] = None) -> set[int]:
    """Season start-years already on the release, parsed from `_{season}.parquet` asset names.

    Returns an empty set if the release does not exist.
    """
    run = runner or (lambda args: _gh_runner(args))
    try:
        out = run(["release", "view", tag, "--repo", repo, "--json", "assets",
                   "--jq", ".assets[].name"])
    except subprocess.CalledProcessError:
        return set()
    return {int(m.group(1)) for line in (out or "").splitlines() if (m := _SEASON_RE.search(line))}


def upload_artifacts(
    artifacts_dir: Path, tag: str, repo: str, *,
    dry_run: bool = False,
    runner: Optional[Callable] = None,
    exists_check: Optional[Callable] = None,
) -> dict:
    """Upload each parquet under *artifacts_dir* to release *tag* on *repo* (creating it if needed).

    ``runner`` (default: real `gh` subprocess) and ``exists_check`` are injectable for tests.
    """
    run = runner or (lambda args: _gh_runner(args))
    exists = exists_check or _gh_release_exists
    files = plan_uploads(artifacts_dir)
    if dry_run:
        return {"uploaded": 0, "files": [f.name for f in files]}
    if not exists(tag, repo):
        run(["release", "create", tag, "--repo", repo, "--title", tag,
             "--notes", f"{tag} datasets (NBA model zoo)"])
    for f in files:
        run(["release", "upload", tag, str(f), "--repo", repo, "--clobber"])
    return {"uploaded": len(files), "files": [f.name for f in files]}
