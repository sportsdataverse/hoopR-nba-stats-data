"""Verbatim raw JSON store for stats.nba.com v3 captures.

SDV `-raw` convention: raw per-game payloads are committed to the repo
value-verbatim (parsed payload re-serialized; JSON-equal, not byte-identical to
the wire) so scraping is incremental/resumable and any downstream reprocess can
rebuild from disk without re-hitting stats.nba.com.

Two layouts
-----------
This repo grew its own store before ``hoopR-nba-stats-raw`` had a scraper, so two
now exist and they are not interchangeable:

``{root}/nba_stats/json/{kind}/{game_id}.json`` (**legacy**, this repo)
    Short kind names, no season directory, and ``boxv3_periods`` is *one file per
    game* holding every period.

``{root}/nba_stats/json/{endpoint}/{season}/{game_id}.json`` (**shared**, the raw repo)
    Endpoint names and a season directory -- what sdv-py's ``_raw_store_path``
    writes and what every other league's store looks like. Per-period boxscores are
    one payload per *game* keyed by period, matching legacy; an earlier sweep wrote
    them split one-per-period and those are still read, so they need no re-fetch.

Readers prefer the shared layout and fall back to legacy, so this repo can migrate
onto ``hoopR-nba-stats-raw`` (a strict superset: ~87k payloads vs ~40k, and the
only one carrying ``gamerotation``) without invalidating committed fixtures or the
existing local store. Writes go to the shared layout.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Union

_KINDS = ("pbpv3", "boxv3", "boxv3_periods")

#: Legacy kind -> the endpoint name the shared store uses.
_ENDPOINT = {
    "pbpv3": "playbyplayv3",
    "boxv3": "boxscoretraditionalv3",
    "boxv3_periods": "boxscoretraditionalv3_period",
}


def season_of(game_id: str) -> int:
    """Season **end** year encoded in a 10-digit NBA game id.

    ``0020500469`` -> 2006. Digits 3-4 are the season's *start* year and an NBA
    season spans two calendar years, so the shared store's directory is start + 1.
    """
    gid = str(game_id).zfill(10)
    yy = int(gid[3:5])
    start = 1900 + yy if yy >= 90 else 2000 + yy
    return start + 1


def _store_root(root: Union[str, Path]) -> Path:
    return Path(root) / "nba_stats" / "json"


def raw_path(root: Union[str, Path], kind: str, game_id: str, suffix: str = "") -> Path:
    """Canonical (shared-layout) path for one raw capture.

    Args:
        root: Repo root holding ``nba_stats/json``.
        kind: One of ``"pbpv3"`` / ``"boxv3"`` / ``"boxv3_periods"``.
        game_id: 10-digit NBA Stats game id.
        suffix: Appended to the stem, e.g. ``"_p1"`` for a single period.

    Returns:
        ``{root}/nba_stats/json/{endpoint}/{season}/{game_id}{suffix}.json``.
    """
    endpoint = _ENDPOINT.get(kind, kind)
    return (
        _store_root(root)
        / endpoint
        / str(season_of(game_id))
        / f"{game_id}{suffix}.json"
    )


def legacy_raw_path(root: Union[str, Path], kind: str, game_id: str) -> Path:
    """This repo's original path: ``{root}/nba_stats/json/{kind}/{game_id}.json``."""
    return _store_root(root) / kind / f"{game_id}.json"


def resolve_raw_path(
    root: Union[str, Path], kind: str, game_id: str
) -> Union[Path, None]:
    """First existing path for a capture, shared layout preferred; None if absent."""
    for candidate in (
        raw_path(root, kind, game_id),
        legacy_raw_path(root, kind, game_id),
    ):
        if candidate.exists():
            return candidate
    return None


def period_paths(root: Union[str, Path], game_id: str) -> list[Path]:
    """Per-period boxscore files for a game in the shared layout, period-ordered."""
    directory = _store_root(root) / _ENDPOINT["boxv3_periods"] / str(season_of(game_id))
    if not directory.is_dir():
        return []

    def period_of(p: Path) -> int:
        tail = p.stem.rsplit("_p", 1)
        return int(tail[1]) if len(tail) == 2 and tail[1].isdigit() else 0

    return sorted(directory.glob(f"{game_id}_p*.json"), key=period_of)


def read_raw(root: Union[str, Path], kind: str, game_id: str) -> Any:
    """Load one capture, from whichever layout has it.

    ``boxv3_periods`` always comes back as ``{period: payload}`` keyed by ``int``,
    whichever way it was stored. The canonical form is one payload per game keyed
    by period; JSON keys are strings, so they are coerced. An earlier sweep wrote
    the periods split one-file-per-game-period, and those are still reassembled so
    that they need no re-fetch.

    Raises:
        FileNotFoundError: If the capture is absent from both layouts.
    """
    if kind == "boxv3_periods":
        found = resolve_raw_path(root, kind, game_id)
        if found is not None:
            combined = json.loads(found.read_text())
            if isinstance(combined, dict):
                return {int(k): v for k, v in combined.items() if str(k).isdigit()}
            return combined
        parts = period_paths(root, game_id)
        if parts:
            return {
                int(path.stem.rsplit("_p", 1)[1]): json.loads(path.read_text())
                for path in parts
            }
        raise FileNotFoundError(
            f"no {kind} capture for {game_id} under {_store_root(root)}"
        )

    found = resolve_raw_path(root, kind, game_id)
    if found is None:
        raise FileNotFoundError(
            f"no {kind} capture for {game_id} under {_store_root(root)}"
        )
    return json.loads(found.read_text())


def write_raw(root: Union[str, Path], kind: str, game_id: str, payload: Any) -> Path:
    """Write *payload* verbatim (``json.dumps``, no reshape) to the shared layout.

    Args:
        root: Repo root holding ``nba_stats/json``.
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
    """Whether all three raw kinds are captured for *game_id*, in either layout."""
    for kind in _KINDS:
        if resolve_raw_path(root, kind, game_id) is not None:
            continue
        if kind == "boxv3_periods" and period_paths(root, game_id):
            continue
        return False
    return True
