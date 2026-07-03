"""Scrape client: proxy rotation + trailing-window rate limiter + injectable v3 transport.

Python port of the R side's ``R/utils.R`` (``get_proxy_ips`` / ``next_proxy`` /
``rate_limit``) for the stats.nba.com v3 play-by-play + box score endpoints.
"""

from __future__ import annotations

from .client import V3Client
from .proxy import RoundRobin, load_proxies, redact
from .rate_limit import TokenBucket

__all__ = ["V3Client", "RoundRobin", "load_proxies", "redact", "TokenBucket"]
