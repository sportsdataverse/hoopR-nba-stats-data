"""V3Client -- stats.nba.com v3 play-by-play + box score fetch client.

Wraps sdv-py's ``nba_stats`` wrappers with a round-robin proxy pool (`.proxy`)
and a shared trailing-window rate limiter (`.rate_limit`). The HTTP call
itself is fully injectable via ``transport=`` so callers (and tests) never
need real network access; ``V3Client()`` with no args defaults to the real
sdv-py wrappers routed through curl_cffi Chrome impersonation
(``sportsdataverse.nba.nba_stats_runtime``).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .proxy import RoundRobin
from .rate_limit import TokenBucket

Transport = Callable[..., dict[str, Any]]

# stats.nba.com boxscore v3 RangeType=2 ("custom range"): StartRange/EndRange
# are cumulative-from-tipoff tenths of a second (deciseconds). This is the
# pbpstats-validated recipe for scoping a box score to exactly one period
# (pbpstats/resources/enhanced_pbp/start_of_period.py in the sibling pbpstats
# checkout). NOTE: sdv-py itself has no `_QUARTER_BOX_RANGE_TYPE` /
# `_period_start_range` constants to import (grepped clean at HEAD) despite
# this module's originating brief sketching an import from
# `sportsdataverse.nba.nba_lineups` -- those symbols don't exist upstream, so
# the constants + formula are defined locally here instead.
_QUARTER_BOX_RANGE_TYPE = 2
_DECISECONDS_PER_QUARTER = 7200  # 12:00 quarter, tenths of a second (NBA/G-League)
_DECISECONDS_PER_OT = 3000  # 5:00 OT, tenths of a second


def _period_start_range(period: int) -> int:
    """Cumulative game-clock deciseconds elapsed at the start of *period* (1-indexed)."""
    if period <= 1:
        return 0
    if period <= 4:
        return _DECISECONDS_PER_QUARTER * (period - 1)
    return 4 * _DECISECONDS_PER_QUARTER + _DECISECONDS_PER_OT * (period - 5)


def _default_transport(kind: str, game_id: str, *, proxy_url: Optional[str] = None, **params: Any) -> dict[str, Any]:
    """Real transport: routes through the sdv-py ``nba_stats`` wrappers (raw dict)."""
    from sportsdataverse.nba.nba_stats import (
        nba_stats_boxscoretraditionalv3,
        nba_stats_playbyplayv3,
    )

    if kind == "pbp":
        return nba_stats_playbyplayv3(game_id=game_id, return_parsed=False, proxy_url=proxy_url)
    return nba_stats_boxscoretraditionalv3(game_id=game_id, return_parsed=False, proxy_url=proxy_url, **params)


class V3Client:
    """Rate-limited, proxy-rotated fetch client for stats.nba.com v3 endpoints.

    Args:
        transport: Injectable callable ``(kind, game_id, **params) -> dict``.
            Defaults to :func:`_default_transport` (real sdv-py wrappers).
        proxies: A :class:`~nba_data_build.scrape.proxy.RoundRobin` instance
            (or anything exposing ``.next() -> Optional[str]``). Defaults to
            an empty (direct, no-proxy) rotation.
        bucket: A :class:`~nba_data_build.scrape.rate_limit.TokenBucket`
            instance. Defaults to one built from the standard
            ``STATS_RATE_*`` env vars.
    """

    def __init__(
        self,
        transport: Optional[Transport] = None,
        proxies: Optional[RoundRobin] = None,
        bucket: Optional[TokenBucket] = None,
    ):
        self._transport: Transport = transport or _default_transport
        self._proxies = proxies if proxies is not None else RoundRobin([])
        self._bucket = bucket if bucket is not None else TokenBucket()

    def _call(self, kind: str, game_id: str, **params: Any) -> dict[str, Any]:
        """Charge the shared rate budget, rotate a proxy, then dispatch one call."""
        self._bucket.acquire()
        proxy_url = self._proxies.next()
        return self._transport(kind, game_id, proxy_url=proxy_url, **params)

    def fetch_pbp(self, game_id: str) -> dict[str, Any]:
        """Fetch the v3 play-by-play payload for one game.

        Args:
            game_id: 10-digit NBA Stats game id (e.g. ``"0022300001"``).

        Returns:
            The raw ``playbyplayv3`` JSON payload (``dict``).
        """
        return self._call("pbp", game_id)

    def fetch_box(self, game_id: str) -> dict[str, Any]:
        """Fetch the whole-game v3 traditional box score payload for one game.

        Args:
            game_id: 10-digit NBA Stats game id.

        Returns:
            The raw ``boxscoretraditionalv3`` JSON payload (``dict``).
        """
        return self._call("box", game_id)

    def fetch_box_periods(self, game_id: str, n_periods: int) -> dict[int, dict[str, Any]]:
        """Fetch one v3 box score payload per period, scoped via ``RangeType=2``.

        Each period issues its own rate-limited + proxy-rotated call (see
        :func:`_period_start_range` for the decisecond-range recipe).

        Args:
            game_id: 10-digit NBA Stats game id.
            n_periods: Number of periods to fetch (4 for regulation, more for OT).

        Returns:
            A dict keyed by period number (1..``n_periods``) -> raw
            ``boxscoretraditionalv3`` JSON payload for that period only.
        """
        out: dict[int, dict[str, Any]] = {}
        for period in range(1, n_periods + 1):
            out[period] = self._call(
                "box",
                game_id,
                start_period="0",
                end_period="0",
                range_type=str(_QUARTER_BOX_RANGE_TYPE),
                start_range=str(_period_start_range(period)),
                end_range=str(_period_start_range(period + 1)),
            )
        return out
