"""Verbatim raw JSON store for stats.nba.com v3 captures.

SDV `-raw` convention: raw per-game payloads are committed to the repo
byte-verbatim (no reshape, no reparse) so scraping is incremental/resumable
and any downstream reprocess can rebuild from disk without re-hitting
stats.nba.com. Layout: ``{root}/nba_stats/json/{kind}/{game_id}.json`` for
``kind`` in ``pbpv3`` / ``boxv3`` / ``boxv3_periods``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Union

_KINDS = ("pbpv3", "boxv3", "boxv3_periods")


def raw_path(root: Union[str, Path], kind: str, game_id: str) -> Path:
    """Return the on-disk path for one raw capture.

    Args:
        root: Raw-store root directory.
        kind: One of ``"pbpv3"`` / ``"boxv3"`` / ``"boxv3_periods"``.
        game_id: 10-digit NBA Stats game id.

    Returns:
        ``{root}/nba_stats/json/{kind}/{game_id}.json``.
    """
    return Path(root) / "nba_stats" / "json" / kind / f"{game_id}.json"


def write_raw(root: Union[str, Path], kind: str, game_id: str, payload: Any) -> Path:
    """Write *payload* verbatim (``json.dumps``, no reshape) to its raw-store path.

    Args:
        root: Raw-store root directory.
        kind: One of ``"pbpv3"`` / ``"boxv3"`` / ``"boxv3_periods"``.
        game_id: 10-digit NBA Stats game id.
        payload: JSON-serializable raw payload, written as-is.

    Returns:
        The path written to.
    """
    path = raw_path(root, kind, game_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return path


def has_raw(root: Union[str, Path], game_id: str) -> bool:
    """Return True iff all three raw kinds are already captured for *game_id*.

    Args:
        root: Raw-store root directory.
        game_id: 10-digit NBA Stats game id.

    Returns:
        Whether ``pbpv3`` + ``boxv3`` + ``boxv3_periods`` all exist on disk.
    """
    return all(raw_path(root, kind, game_id).exists() for kind in _KINDS)
