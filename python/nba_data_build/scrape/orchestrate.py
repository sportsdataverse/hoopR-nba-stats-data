"""Sequential, resumable per-game scrape orchestration.

Drives :class:`~nba_data_build.scrape.client.V3Client` against the verbatim
raw store (:mod:`~nba_data_build.scrape.raw_store`): skip games already fully
captured (unless ``rescrape=True``), otherwise fetch pbpv3 + boxv3 +
boxv3_periods and write all three verbatim. Row-level game discovery (finished
vs. live/TBD) is expected to come from ``sportsdataverse.nba.nba_schedule``
upstream (Task 10 drives this module against that output).

Deliberately **no parallelism** -- :class:`~nba_data_build.scrape.client.V3Client`
shares one proxy rotation + one trailing-window rate-limit bucket per process,
and both are documented sequential-only (see ``rate_limit.py``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping, Sequence, Union

from .client import V3Client
from .raw_store import has_raw, write_raw

logger = logging.getLogger(__name__)

_FINISHED_STATUS = 3


def scrape_game(
    client: V3Client,
    root: Union[str, Path],
    game_id: str,
    n_periods: int,
    *,
    rescrape: bool = False,
) -> bool:
    """Scrape and verbatim-write one game's pbpv3 + boxv3 + boxv3_periods.

    Skips the game (returns ``False``) if all three raw kinds are already on
    disk and ``rescrape`` is not set -- the resumable/incremental contract
    that lets a re-run of the scraper never repeat already-captured games.

    Args:
        client: Injected :class:`V3Client` (real or test transport).
        root: Raw-store root directory.
        game_id: 10-digit NBA Stats game id.
        n_periods: Number of periods to fetch for ``boxv3_periods``
            (4 for regulation, more for OT games).
        rescrape: When True, re-fetch and overwrite even if already captured.

    Returns:
        True if this call fetched and wrote the game, False if skipped.
    """
    if has_raw(root, game_id) and not rescrape:
        logger.info("scrape_game: skip %s (already captured)", game_id)
        return False

    write_raw(root, "pbpv3", game_id, client.fetch_pbp(game_id))
    write_raw(root, "boxv3", game_id, client.fetch_box(game_id))
    write_raw(root, "boxv3_periods", game_id, client.fetch_box_periods(game_id, n_periods))
    logger.info("scrape_game: wrote %s", game_id)
    return True


def scrape_finished_games(
    client: V3Client,
    root: Union[str, Path],
    game_rows: Sequence[Mapping[str, Any]],
    *,
    rescrape: bool = False,
) -> list[str]:
    """Sequentially scrape every finished, non-TBD game in *game_rows*.

    Filters to ``game_status == 3`` (finished) and ``home_team_id != 0``
    (excludes all-star / TBD placeholder rows), then calls :func:`scrape_game`
    once per row in order -- no parallelism, since the shared rate-limit
    bucket and proxy rotation on *client* are sequential-only.

    Args:
        client: Injected :class:`V3Client` (real or test transport).
        root: Raw-store root directory.
        game_rows: Schedule rows (e.g. from
            ``sportsdataverse.nba.nba_schedule``), each with ``game_id`` /
            ``game_status`` / ``home_team_id`` and optionally ``n_periods``
            (default 4 when absent).
        rescrape: Passed through to :func:`scrape_game` for every row.

    Returns:
        The ``game_id`` values that were actually fetched and written (skips
        omitted).
    """
    written: list[str] = []
    failed: list[str] = []
    for row in game_rows:
        if int(row["game_status"]) != _FINISHED_STATUS or int(row["home_team_id"]) == 0:
            continue
        game_id = row["game_id"]
        n_periods = int(row.get("n_periods", 4))
        # ponytail: retry-then-skip -- a transient transport failure (proxy
        # connect timeout etc.) must not kill a 1,400-game season run; the raw
        # store is resumable, so a skipped game is picked up by the next run.
        for attempt in (1, 2, 3):
            try:
                if scrape_game(client, root, game_id, n_periods, rescrape=rescrape):
                    written.append(game_id)
                break
            except Exception as exc:  # noqa: BLE001 -- transport errors vary by backend
                logger.warning(
                    "scrape_game %s attempt %d/3 failed: %s", game_id, attempt, str(exc)[:200]
                )
        else:
            failed.append(game_id)
    if failed:
        logger.warning(
            "scrape_finished_games: %d game(s) failed after retries: %s",
            len(failed),
            failed[:20],
        )
    return written
