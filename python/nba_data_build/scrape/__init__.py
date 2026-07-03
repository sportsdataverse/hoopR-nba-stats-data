"""Scrape client: proxy rotation + trailing-window rate limiter + injectable v3 transport.

Python port of the R side's ``R/utils.R`` (``get_proxy_ips`` / ``next_proxy`` /
``rate_limit``) for the stats.nba.com v3 play-by-play + box score endpoints,
plus the verbatim raw store + sequential resumable scrape orchestration that
sit on top of it (:mod:`raw_store`, :mod:`orchestrate`).
"""

from __future__ import annotations

from .client import V3Client
from .orchestrate import scrape_finished_games, scrape_game
from .proxy import RoundRobin, load_proxies, redact
from .rate_limit import TokenBucket
from .raw_store import has_raw, raw_path, write_raw

__all__ = [
    "V3Client",
    "RoundRobin",
    "load_proxies",
    "redact",
    "TokenBucket",
    "raw_path",
    "write_raw",
    "has_raw",
    "scrape_game",
    "scrape_finished_games",
]
