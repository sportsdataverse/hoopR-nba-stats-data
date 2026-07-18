#!/usr/bin/env python
"""Backfill the raw JSON store for games already in the possession cache.

The read-through raw store (sdv-py ``nba_possessions``, env
``SDV_PY_NBA_RAW_JSON_DIR``) persists payloads as a side effect of fetching.
Games warmed BEFORE the store landed have their possession parquet but no
retained JSON — this script calls the same store-routed fetchers for exactly
the endpoints that are missing on disk, so completed games are skipped
without a parse and every fetch persists its payload. Idempotent; Ctrl-C
and rerun any time.

Fetch-only (no possession compute) — I/O-bound, so threads are fine and the
worker count is about proxy courtesy, not RAM. ``gamerotation`` failures are
counted but not fatal: the endpoint legitimately has no data for old seasons.
Per-period boxscores (the degraded-rotation fallback) are NOT backfilled —
whether a game needed them isn't recorded, and the store captures them on
any future compile that takes that path.

Run:
    cd python && SDV_PY_NBA_RAW_JSON_DIR=/mnt/sdv_repos/hoopR-nba-stats-raw/nba_stats/json \\
      uv run python ../scripts/backfill_raw_json.py
"""

from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

WORKERS = int(os.environ.get("BACKFILL_WORKERS", "6"))
CACHE = Path(os.environ.get("SDV_PY_NBA_CACHE_DIR", "/data/nba_possessions")) / "possessions"


def _log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%F %T')}Z] {msg}", flush=True)


def main() -> int:
    if not os.environ.get("SDV_PY_NBA_RAW_JSON_DIR"):
        print("SDV_PY_NBA_RAW_JSON_DIR must be set (raw store root)", file=sys.stderr)
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
    from nba_data_build.scrape.proxy import RoundRobin, load_proxies
    from sportsdataverse.nba.nba_possessions import (
        _fetch_box,
        _fetch_pbp,
        _fetch_rotation,
        _raw_store_path,
    )

    endpoints = (
        ("playbyplayv3", _fetch_pbp),
        ("boxscoretraditionalv3", _fetch_box),
        ("gamerotation", _fetch_rotation),
    )
    game_ids = sorted({p.name.split("__")[0] for p in CACHE.glob("*.parquet")})
    todo = [
        gid
        for gid in game_ids
        if any(not _raw_store_path(ep, gid).exists() for ep, _ in endpoints)  # type: ignore[union-attr]
    ]
    _log(f"{len(game_ids)} cached games, {len(todo)} with missing raw JSON, workers={WORKERS}")
    if not todo:
        return 0

    rr = RoundRobin(load_proxies())

    def _one(gid: str) -> tuple[str, int, int]:
        fetched = failed = 0
        for ep, fetcher in endpoints:
            path = _raw_store_path(ep, gid)
            if path is not None and path.exists():
                continue
            try:
                fetcher(gid, proxy_url=rr.next())
                fetched += 1
            except Exception:  # noqa: BLE001 - a game-local failure must not kill the sweep
                failed += 1
        return gid, fetched, failed

    done = fetch_total = fail_total = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for fut in as_completed(pool.submit(_one, gid) for gid in todo):
            gid, fetched, failed = fut.result()
            done += 1
            fetch_total += fetched
            fail_total += failed
            if done % 250 == 0 or done == len(todo):
                _log(f"{done}/{len(todo)} games | {fetch_total} payloads fetched | {fail_total} endpoint misses")
    _log(
        f"backfill complete: {fetch_total} payloads persisted, {fail_total} endpoint misses (rotation gaps expected pre-~2015)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
