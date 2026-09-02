"""Reader for the ``hoopR-nba-stats-raw`` store — the only input the reshaper has.

Every dataset compiled here is reshaped from payloads that ``hoopR-nba-stats-raw``
already captured — this repo never calls stats.nba.com. Point ``root`` at a fixture
tree or a sibling checkout and the whole pipeline runs offline, which is what makes
the builders testable; point it at :data:`RAW_BASE` and the same code reads each JSON
file over HTTP instead (what the daily workflow does, having no checkout of the store).

The store has two layouts, because the endpoints are keyed differently:

``{endpoint}/{dir}/{game_id}.json``
    Per-game payloads (``playbyplayv3``, ``boxscoretraditionalv3``,
    ``boxscoresummaryv2`` and the per-period boxscore variant). Because an NBA season
    spans two calendar years, the store keys these by the season **end** year
    (``dir = start + 1``). :func:`game_season_of` decodes that end year straight from
    the 10-digit game id (reused from ``scrape.raw_store`` so the reader and the
    writer can never drift), and :func:`store_dir` maps a **start-year** season arg to
    the same end-year directory when listing a season's games.

``{endpoint}/{season}/{variant}.json`` or ``{endpoint}/{season}.json``
    Season-level payloads (standings, season stats, lineups, rosters, draft, and the
    ``leaguegamelog`` game index). These are keyed by the season **start** year, so
    ``dir = season`` — no shift.

The split between the two keyings lives in exactly one place, :func:`store_dir`; every
reader routes season→dir through it.

``root`` may be a local checkout or the ``raw.githubusercontent.com`` base URL, so a
job can run against a sibling clone on disk or read the tree straight from GitHub.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..scrape.raw_store import season_of as game_season_of

RAW_BASE = (
    "https://raw.githubusercontent.com/sportsdataverse/hoopR-nba-stats-raw/main/nba_stats/json"
)

# Per-game endpoints are keyed by the season END year (start + 1); every other
# endpoint is keyed by the season START year. This tuple is the whole basis of the
# split -- store_dir() is the one function that consults it.
GAME_ENDPOINTS = (
    "playbyplayv3",
    "boxscoretraditionalv3",
    "boxscoretraditionalv3_period",
    "boxscoresummaryv2",
    "boxscorematchupsv3",
)


def store_dir(endpoint: str, season: int) -> int:
    """Store directory (year) holding ``endpoint``'s payloads for a start-year season.

    Game endpoints key by the season **end** year (``season + 1``); league/season-level
    endpoints key by the **start** year (``season``). This is the single point where the
    NBA start↔end split is applied — every reader passes season through here rather than
    hardcoding the shift, so the two keyings can never disagree by accident.
    """
    return season + 1 if endpoint in GAME_ENDPOINTS else season


def _is_url(root: str | Path) -> bool:
    return str(root).startswith(("http://", "https://"))


def _http_retries() -> int:
    """Transient-error attempts beyond the first. ``SDV_PY_HTTP_RETRIES`` bounds it."""
    try:
        return max(0, int(os.environ.get("SDV_PY_HTTP_RETRIES", "3")))
    except ValueError:
        return 3


def _read_json(root: str | Path, rel: str) -> Any | None:
    """Load ``rel`` under ``root`` from disk or over HTTP; ``None`` when absent.

    "Absent" means the store never captured it: a local miss, or a 404. Every
    OTHER HTTP failure -- 5xx, a rate-limit, a dropped connection, a timeout --
    is TRANSIENT, and must not be reported as absence.

    This used to soft-miss all of them, on the reasoning that a blip should not
    abort a whole season mid-build. The trade is the other way round: a season
    reads ~1,300 per-game payloads over HTTP, so one swallowed 5xx is one game
    silently missing from a PUBLISHED season, on a green run, with nothing in
    the log. A failed build is recoverable in a way a quietly-truncated release
    is not -- the twin (wehoop-wnba-stats-data) reached the same conclusion the
    hard way after 33 days of green runs that published nothing. Retry with
    backoff, then raise.

    The LOCAL branch is unchanged: a missing or corrupt file stays a soft miss.
    A gap in a checked-out store is real and expected, and a corrupt file is a
    permanent local fact rather than something a retry could fix. Only the
    OSError catch went away with the reasoning that justified it -- it existed
    to "match the HTTP branch's failure semantics", and those semantics are the
    thing this change reverses.
    """
    if _is_url(root):
        url = f"{str(root).rstrip('/')}/{rel}"
        attempts = _http_retries() + 1
        for attempt in range(1, attempts + 1):
            try:
                with urllib.request.urlopen(url, timeout=60) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                if exc.code in (404, 410):
                    return None  # never captured; retrying cannot change that
                if attempt == attempts:
                    raise
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                if attempt == attempts:
                    raise
            time.sleep(min(2 ** (attempt - 1), 8))
        return None
    path = Path(root) / rel
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def game_payload_path(root: str | Path, endpoint: str, game_id: str) -> Path:
    """On-disk path of a per-game payload (local roots only).

    The directory is decoded from the game id itself (season end year), so this is
    correct regardless of which start-year season the caller thinks the game belongs to.
    """
    return Path(root) / endpoint / str(game_season_of(game_id)) / f"{str(game_id).zfill(10)}.json"


def read_game(root: str | Path, endpoint: str, game_id: str) -> Any | None:
    """One per-game payload, or ``None`` if the raw store never captured it."""
    gid = str(game_id).zfill(10)
    return _read_json(root, f"{endpoint}/{game_season_of(gid)}/{gid}.json")


def read_season(
    root: str | Path, endpoint: str, season: int, variant: str | None = None
) -> Any | None:
    """One season-level payload, or ``None`` if absent.

    ``season`` is the start-year label; the directory is resolved through
    :func:`store_dir`. ``variant`` matches the raw repo's slug (``regular-season``,
    ``playoffs``, ``base_totals``, a team id for ``commonteamroster``); omit it for
    unparameterized endpoints written as a bare ``{season}.json``.
    """
    sd = store_dir(endpoint, season)
    rel = f"{endpoint}/{sd}/{variant}.json" if variant else f"{endpoint}/{sd}.json"
    return _read_json(root, rel)


def available_games(root: str | Path, endpoint: str, season: int) -> list[str]:
    """Game ids captured for ``endpoint`` in ``season`` (local roots only).

    ``season`` is the start-year label; the directory read is
    ``store_dir(endpoint, season)`` (end year for game endpoints). Enumerating a URL
    root is not supported — GitHub serves files, not listings — so callers working
    against RAW_BASE should drive from :func:`season_game_ids`.
    """
    if _is_url(root):
        raise ValueError("available_games needs a local root; use season_game_ids for URLs")
    d = Path(root) / endpoint / str(store_dir(endpoint, season))
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def _result_sets(payload: Any) -> list:
    """The envelope's result sets, however it spells them.

    stats.nba.com returns ``resultSets`` (plural, a list) on most endpoints but
    ``resultSet`` (singular, sometimes a bare object) on others. Readers that
    know only the plural form silently see zero rows on the singular shape, so
    both spellings are normalised here and every reader routes through it.
    """
    if not isinstance(payload, dict):
        return []
    sets = payload.get("resultSets") or payload.get("resultSet") or []
    if isinstance(sets, dict):
        sets = [sets]
    return [rs for rs in sets if isinstance(rs, dict)]


def season_game_ids(root: str | Path, season: int) -> list[str]:
    """Every game id for ``season`` from the captured ``leaguegamelog`` payloads.

    This is the authoritative index — it covers games whose per-game payloads have
    not been captured yet, which :func:`available_games` by definition cannot.
    ``leaguegamelog`` is a season-level endpoint, so it reads from the start-year dir.
    """
    out: set[str] = set()
    for stype in ("regular-season", "playoffs"):
        payload = read_season(root, "leaguegamelog", season, stype)
        for rs in _result_sets(payload):
            headers = [str(h).upper() for h in rs.get("headers") or []]
            if "GAME_ID" not in headers:
                continue
            idx = headers.index("GAME_ID")
            for row in rs.get("rowSet") or []:
                if row[idx] is not None:
                    out.add(str(row[idx]).zfill(10))
    return sorted(out)


def iter_game_payloads(
    root: str | Path, endpoint: str, game_ids: list[str]
) -> Iterator[tuple[str, Any]]:
    """Yield ``(game_id, payload)`` for each captured game, skipping misses.

    A generator so a season compiles without holding every payload at once — a
    season of play-by-play is hundreds of MB of JSON.
    """
    for gid in game_ids:
        payload = read_game(root, endpoint, gid)
        if payload is not None:
            yield gid, payload


def season_payload(
    root: str | Path, endpoint: str, season: int, variant: str | None = None
) -> Any | None:
    """Alias of :func:`read_season` — the name game-level builders call for symmetry."""
    return read_season(root, endpoint, season, variant)


def result_set(payload: Any, name: str | None = None) -> tuple[list[str], list[list[Any]]]:
    """``(headers, rows)`` from a stats.com ``resultSets`` envelope.

    Returns the named set, or the first non-empty one when ``name`` is omitted.
    Empty/malformed payloads give ``([], [])`` rather than raising, so callers can
    build a zero-row frame with the documented schema instead of null-checking.
    """
    for rs in _result_sets(payload):
        if name is not None and str(rs.get("name")) != name:
            continue
        headers = [str(h) for h in rs.get("headers") or []]
        rows = [list(r) for r in rs.get("rowSet") or []]
        if name is not None or rows:
            return headers, rows
    return [], []
