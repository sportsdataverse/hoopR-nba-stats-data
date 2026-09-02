"""Publish built parquet to sportsdataverse-data GitHub releases (gh CLI)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, Optional

from sportsdataverse.release import upload_release_sidecars

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


#: Release sidecar metadata: the loader a consumer reads each tag through.
#: R's sportsdataverse_save() writes this as package_function.txt/.json beside
#: every published asset; this repo's hand-rolled `gh release upload` dropped it
#: along with the timestamp pair. Values that the R producer already published to
#: a tag are reused verbatim; the rest name the hoopR/sdv-py loader. A tag that is not
#: listed still gets its timestamp re-stamped -- it just ships no package_function,
#: which leaves whatever is already on the release untouched.
PKG_FUNCTION: dict[str, str] = {
    "nba_stats_coaches": "sportsdataverse.nba.load_nba_stats_coaches()",
    "nba_stats_game_lineups": "sportsdataverse.nba.load_nba_stats_lineups_v3()",
    "nba_stats_game_rosters": "sportsdataverse.nba.load_nba_stats_game_rosters()",
    "nba_stats_lineups": "sportsdataverse.nba.load_nba_stats_lineups()",
    "nba_stats_officials": "sportsdataverse.nba.load_nba_stats_officials()",
    "nba_stats_pbp": "sportsdataverse.nba.load_nba_stats_pbp()",
    "nba_stats_player_boxscores": "sportsdataverse.nba.load_nba_stats_player_boxscores()",
    "nba_stats_player_game_logs": "sportsdataverse.nba.load_nba_stats_player_game_logs()",
    "nba_stats_player_season_stats": "sportsdataverse.nba.load_nba_stats_player_season_stats()",
    "nba_stats_possessions": "sportsdataverse.nba.load_nba_stats_possessions()",
    "nba_stats_rosters": "sportsdataverse.nba.load_nba_stats_rosters()",
    "nba_stats_schedules": "hoopR::load_nba_schedule()",
    "nba_stats_shots": "sportsdataverse.nba.load_nba_stats_shots()",
    "nba_stats_standings": "sportsdataverse.nba.load_nba_stats_standings()",
    "nba_stats_team_boxscores": "sportsdataverse.nba.load_nba_stats_team_boxscores()",
    "nba_stats_team_season_stats": "sportsdataverse.nba.load_nba_stats_team_season_stats()",
}

def plan_uploads(
    artifacts_dir: Path,
    seasons: Optional[Iterable[int]] = None,
    *,
    pattern: str = "*.parquet",
    exts: tuple[str, ...] = ("parquet",),
) -> list[Path]:
    """Return the files under *artifacts_dir* to upload (sorted).

    Two selection modes:

    * default (``pattern="*.parquet"``): glob each extension in *exts* and,
      when *seasons* is given, keep only files ending in ``_{season}.{ext}``
      for one of those seasons. *exts* defaults to ``("parquet",)`` so existing
      callers (the v3/modeling tags) are parquet-only exactly as before; the
      reshaper passes ``("parquet","rds","csv")`` because ``hoopR::load_nba_*()``
      reads the ``.rds`` and the release is the only channel that ships it.
      Season scoping avoids re-uploading the whole backfill-to-date on every
      single-season call (O(n^2) across a multi-season run).
    * custom *pattern* (e.g. a model-card ``*_card.json`` sidecar): returned
      unscoped, *exts* ignored.
    """
    if pattern != "*.parquet":
        return sorted(Path(artifacts_dir).glob(pattern))
    files = sorted(f for ext in exts for f in Path(artifacts_dir).glob(f"*.{ext}"))
    if seasons is None:
        return files
    suffixes = tuple(f"_{s}.{ext}" for s in seasons for ext in exts)
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
    exts: tuple[str, ...] = ("parquet",),
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
    files = plan_uploads(artifacts_dir, seasons, pattern=pattern, exts=exts)
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
    # stamp LAST so the timestamp describes a finished upload, and only when
    # something actually uploaded -- a stamp on a no-op run would claim data
    # moved when it did not
    if uploaded:
        upload_release_sidecars(tag, runner=run, pkg_function=PKG_FUNCTION.get(tag), repo=repo)
    return {
        "uploaded": len(uploaded),
        "failed": failed,
        "files": [f.name for f in files],
    }
