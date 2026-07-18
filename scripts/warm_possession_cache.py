#!/usr/bin/env python
"""Warm the per-game possession cache in parallel, so the model build can stay sequential.

WHY THIS EXISTS (measured on sdv-data 2026-07-17, not assumed):

  per game:  30.1s CPU (86%)  |  5.0s network across 3 fetches (14%)

The backfill is **compute-bound**, not fetch-bound. ``P0_DROPLET_RUNBOOK.md``
says "One process, sequential -- never parallelize the fetch loop; the budget is
per-source, not per-process". That rule is correct for the R scraper (which only
fetches and writes JSON) but does not describe this pipeline, which spends 86% of
each game building enhanced pbp, deriving lineups, and constructing the
possession stint matrix in polars. Sequentially that is ~13 days for 1997:2026 --
not the runbook's 2.5-3 -- with 7 of 8 cores idle.

The request budget is also not binding. Probed the same day:

  conc=1   103 req/min   0 rejected
  conc=32 1707 req/min   0 rejected   (~68x the documented ~25 req/min, no ceiling found)

So: parallelize the CACHE WARM (per-game work, embarrassingly parallel), then run
the existing builder sequentially against a warm cache -- where it is CPU-only and
the seasons still build earliest->latest, leaving the adj-RAPM prior chain and the
season-granular DARKO panel exactly as designed.

WORKER COUNT IS BOUNDED BY RAM AND A LIVE DATABASE, NOT BY CORES:
  * postgres (sdv-db) serves live traffic on this droplet -- leave it headroom.
  * ``compile_nba_season`` accumulates every game's frame in memory before
    concatenating, so each worker holds a whole season (~1-2 GB). ~8 GB free.
Default 5. Raise only after watching RSS.

Resumable: the per-game parquet cache IS the checkpoint. Ctrl-C and rerun; only
uncached games refetch.

SEASONS passed on the command line are now END years, matching
``compile_nba_season``'s season-arg convention (2024 = 2023-24) -- the
per-game possession cache is keyed by game_id, so already-warmed games stay
valid regardless of which season label discovered them.

Run:
    cd python && SDV_PY_NBA_CACHE_DIR=/data/nba_possessions \
      SDV_PY_NBA_RAW_JSON_DIR=/mnt/sdv_repos/hoopR-nba-stats-raw/nba_stats/json \
      uv run python ../scripts/warm_possession_cache.py 1997:2026

``SDV_PY_NBA_RAW_JSON_DIR`` enables sdv-py's read-through raw store: every
stats.nba.com payload a worker fetches is persisted to the raw repo as
``{endpoint}/{season}/{game_id}.json`` (and served from there without a
fetch when present). See scripts/backfill_raw_json.py for games warmed
before the store existed.
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone

SEASON_TYPES = ("Regular Season", "Playoffs")
WORKERS = int(os.environ.get("WARM_WORKERS", "5"))
DELAY_S = float(os.environ.get("SDV_NBA_DELAY_S", "0"))  # network is 14% and unthrottled


def _log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%F %T')}Z] {msg}", flush=True)


def _parse_seasons(spec: str) -> list:
    if ":" in spec:
        lo, hi = spec.split(":", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(spec)]


def _warm(unit) -> dict:
    """Compile one (season, season_type) so its per-game parquet lands in the cache.

    Runs in its own process -- the work is CPU-bound, so threads would just
    contend on the GIL.
    """
    season, stype = unit
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/python")
    from nba_data_build.scrape.proxy import RoundRobin, load_proxies
    from sportsdataverse.nba.nba_season_compile import compile_nba_season

    t0 = time.monotonic()
    try:
        rr = RoundRobin(load_proxies())
        # Do NOT pass cache_dir. compile_nba_season's _default_cache_dir() resolves
        # to $SDV_PY_NBA_CACHE_DIR / "possessions" -- passing cache_dir explicitly
        # bypasses that "possessions" suffix, so the warm would write one directory
        # ABOVE where the builder reads. A silent no-op warm: hours of work, no
        # error, and the builder refetches everything. Let the env var drive both.
        df = compile_nba_season(
            season,
            season_type=stype,
            delay_s=DELAY_S,
            proxy_provider=rr.next,
        )
        return {
            "season": season,
            "stype": stype,
            "rows": df.height,
            "secs": time.monotonic() - t0,
            "error": None,
        }
    except Exception as exc:  # a season-local failure must not kill the sweep
        return {
            "season": season,
            "stype": stype,
            "rows": 0,
            "secs": time.monotonic() - t0,
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> int:
    spec = sys.argv[1] if len(sys.argv) > 1 else "1997:2026"
    seasons = _parse_seasons(spec)
    # Largest first: regular seasons (~1230 games) before playoffs (~85), so the
    # long poles start early and the tail packs into the idle workers.
    units = [(s, t) for t in SEASON_TYPES for s in seasons]

    cache = os.environ.get("SDV_PY_NBA_CACHE_DIR", "(default)")
    _log(f"warming {len(units)} units ({len(seasons)} seasons x {len(SEASON_TYPES)} types)")
    _log(f"workers={WORKERS}  delay_s={DELAY_S}  cache={cache}")
    _log("bounded by RAM + live postgres on this box, NOT by the request budget")

    done = 0
    failed = []
    t0 = time.monotonic()
    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(_warm, u): u for u in units}
        for fut in as_completed(futs):
            r = fut.result()
            done += 1
            tag = f"{r['season']} {r['stype']}"
            if r["error"]:
                failed.append((tag, r["error"]))
                _log(f"  [{done}/{len(units)}] {tag}: FAILED after {r['secs']:.0f}s -- {r['error']}")
            else:
                _log(
                    f"  [{done}/{len(units)}] {tag}: {r['rows']} poss in {r['secs'] / 60:.0f}m "
                    f"| elapsed {(time.monotonic() - t0) / 3600:.1f}h"
                )

    _log("---- summary ----")
    _log(f"  units={len(units)} ok={len(units) - len(failed)} failed={len(failed)}")
    _log(f"  wall clock: {(time.monotonic() - t0) / 3600:.1f}h")
    for tag, err in failed:
        _log(f"  FAILED {tag}: {err}")
    if failed:
        # An empty compile is indistinguishable from a network failure by exit code
        # alone -- that is this pipeline's failure mode of record. Say so loudly.
        _log("RERUN to retry the failures -- the per-game cache makes it cheap.")
        return 1
    _log("cache warm. Now run the sequential build; it will be CPU-only and fast.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
