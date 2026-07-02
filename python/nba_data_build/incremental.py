"""Decide which recent seasons still need compiling + publishing."""
from __future__ import annotations


def detect_missing_seasons(published: set[int], current: int, first: int = 2021) -> list[int]:
    """Return the sorted seasons in ``first..current`` not already published.

    Args:
        published: Season start-years already on the release (parsed from asset names).
        current: The target through-season start-year (inclusive).
        first: The earliest season to consider (default 2021, the harness report floor).

    Returns:
        Ascending list of missing season start-years (empty if all present).
    """
    return [s for s in range(first, current + 1) if s not in published]
