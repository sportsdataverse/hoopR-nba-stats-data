"""Season-level league-dash scrape for the stats.nba.com / stats.wnba.com
``leaguedash*`` endpoints (player/team season stats, bio, lineups, standings,
player tracking).

Unlike the per-game v3 scrape (:mod:`orchestrate`), each of these endpoints is
ONE call per ``(league, season)``. This module reuses the shared proxy pool
(:class:`~nba_data_build.scrape.proxy.RoundRobin`) and rate limiter
(:class:`~nba_data_build.scrape.rate_limit.TokenBucket`) so all stats.nba.com
traffic shares one request budget. Each call returns one tidy polars frame,
tagged with ``season`` + ``league_id`` (the raw payloads carry no clean season
column), suitable for one parquet per ``(endpoint, season)``.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable, Optional

import polars as pl

from .proxy import RoundRobin
from .rate_limit import TokenBucket

# Injectable for offline tests: (module, fn_name, kwargs) -> polars/pandas frame | dict.
Transport = Callable[[str, str, dict], Any]


@dataclass(frozen=True)
class Endpoint:
    """One season-level league-dash dataset.

    Attributes:
        table: output dataset name (release tag suffix), e.g. ``"player_stats"``.
        slug: the ``nba_stats_``/``wnba_stats_`` wrapper suffix, e.g. ``"leaguedashplayerstats"``.
        wnba: whether the endpoint also exists on stats.wnba.com.
    """

    table: str
    slug: str
    wnba: bool = True


# Curated surface — each verified to return a clean single-result-set frame.
# (team_stats dropped: leaguedashteamstats returns an empty payload via the wrapper.)
ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint("player_stats", "leaguedashplayerstats"),
    Endpoint("player_bio", "leaguedashplayerbiostats"),
    Endpoint("lineups", "leaguedashlineups"),
    Endpoint("standings", "leaguestandingsv3"),
    Endpoint("player_tracking", "leaguedashptstats", wnba=False),  # NBA only
)

# league -> (sdv-py module, wrapper prefix, LeagueID)
_LEAGUE: dict[str, tuple[str, str, str]] = {
    "nba": ("sportsdataverse.nba.nba_stats", "nba_stats", "00"),
    "wnba": ("sportsdataverse.wnba.wnba_stats", "wnba_stats", "10"),
}


def season_str(year: int, league: str) -> str:
    """stats API season string: NBA ``2024`` -> ``"2023-24"``; WNBA ``2024`` -> ``"2024"``."""
    return f"{year - 1}-{str(year)[-2:]}" if league == "nba" else str(year)


def endpoints_for(league: str) -> tuple[Endpoint, ...]:
    """The curated endpoints available for ``league`` (WNBA has no player tracking)."""
    return tuple(e for e in ENDPOINTS if league == "nba" or e.wnba)


def _default_transport(module: str, fn_name: str, kwargs: dict) -> Any:
    return getattr(importlib.import_module(module), fn_name)(**kwargs)


class LeagueDashClient:
    """Proxy-rotated, rate-limited season-level league-dash fetch.

    Construct with the shared :class:`RoundRobin` + :class:`TokenBucket` so this
    traffic counts against the same stats.nba.com budget as the per-game scrape.
    ``transport`` is injectable for offline tests.
    """

    def __init__(
        self,
        proxies: RoundRobin,
        bucket: TokenBucket,
        *,
        transport: Optional[Transport] = None,
    ) -> None:
        self._proxies = proxies
        self._bucket = bucket
        self._transport = transport or _default_transport

    def fetch(self, ep: Endpoint, league: str, season: int) -> pl.DataFrame:
        """One rate-limited, proxy-rotated call for ``(endpoint, league, season)``.

        Returns a ``season``+``league_id``-tagged frame, or an empty frame if the
        endpoint yields no rows for that season (a normal upstream gap).
        """
        module, prefix, lid = _LEAGUE[league]
        self._bucket.acquire()
        raw = self._transport(
            module,
            f"{prefix}_{ep.slug}",
            {
                "season": season_str(season, league),
                "league_id": lid,
                "proxy_url": self._proxies.next(),
            },
        )
        if isinstance(raw, dict):  # multi-result-set payload -> take the first set
            raw = next(iter(raw.values()), None)
        if raw is None:
            return pl.DataFrame()
        df = raw if isinstance(raw, pl.DataFrame) else pl.from_pandas(raw)
        if df.is_empty():
            return df
        return df.with_columns(
            pl.lit(season).alias("season"), pl.lit(lid).alias("league_id")
        )
