"""Trailing-window token bucket for the shared stats.nba.com request budget.

Port of the R side's ``R/utils.R::rate_limit`` (see the repo root ``CLAUDE.md``
"Gotchas" section): stats.nba.com shares a request budget across ALL endpoint
types (empirically ~200-300 requests / 10 min). Callers budget one game as
``n_hits`` requests (default 3, since a pbp game hits several endpoints). The
limiter is sequential-only by design -- do not call ``acquire()`` from
parallel workers, its state lives only in the calling process.
"""

from __future__ import annotations

import os
import time


def _envi(name: str, default: int) -> int:
    """Read an int env var, falling back to *default* on missing/invalid value."""
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class TokenBucket:
    """Trailing-window token bucket over a shared request budget.

    Args:
        n_hits: Requests to charge per ``acquire()`` call. Defaults to
            ``STATS_RATE_HITS`` (env, default 3), floored at 1.
        max_calls: Max requests allowed inside the trailing window. Defaults
            to ``STATS_RATE_MAX`` (env, default 250).
        window_s: Trailing-window length in seconds. Defaults to
            ``STATS_RATE_WINDOW`` (env, default 600).
    """

    def __init__(
        self,
        n_hits: int | None = None,
        max_calls: int | None = None,
        window_s: float | None = None,
    ):
        self.n_hits = max(1, n_hits if n_hits is not None else _envi("STATS_RATE_HITS", 3))
        self.max_calls = max_calls if max_calls is not None else _envi("STATS_RATE_MAX", 250)
        self.window_s = float(window_s if window_s is not None else _envi("STATS_RATE_WINDOW", 600))
        self._ts: list[float] = []

    def acquire(self) -> None:
        """Block (if needed) until charging ``n_hits`` requests fits the window, then record them."""
        now = time.monotonic()
        self._ts = [t for t in self._ts if t > now - self.window_s]
        while len(self._ts) + self.n_hits > self.max_calls and self._ts:
            wait = (self._ts[0] + self.window_s) - now + 0.05
            time.sleep(max(0.05, wait))
            now = time.monotonic()
            self._ts = [t for t in self._ts if t > now - self.window_s]
        self._ts.extend([now] * self.n_hits)
