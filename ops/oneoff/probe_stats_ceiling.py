#!/usr/bin/env python
"""Find the REAL stats.nba.com concurrency ceiling from this host.

An earlier probe sustained ~101 req/min with zero rejections -- but that was
just where ``sleep(0.2)`` landed, not a limit. The ceiling is unknown, and it
decides the worker count for the 25-season backfill (~13 days sequential at the
observed 37s/game).

Ramps CONCURRENCY, not sleep. Each worker holds its own proxy IP, so level N
means N distinct exit IPs in flight. Probes ``playbyplayv3`` -- the big payload
that actually dominates per-game latency, not the small boxscore the earlier
probe used.

Two things can break as concurrency rises, and they mean opposite things:
  * REJECTIONS appear   -> a real limit. Back off to the last clean level.
  * LATENCY inflates but rejections stay 0 -> saturation, not throttling; the
    proxies or this host are the bottleneck and more workers stop helping.

Failure signature: stats.nba.com does NOT error -- ``_get`` maps a non-200/blank
body to ``{}``. An empty dict IS the rejection.

Run (R cron disabled first):
    cd python && uv run python ../scripts/probe_stats_ceiling.py
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

LEVELS = [int(x) for x in os.environ.get("PROBE_LEVELS", "1,4,8,16,24,32").split(",")]
PER_LEVEL = int(os.environ.get("PROBE_PER_LEVEL", "32"))
REJECT_ABORT_PCT = float(os.environ.get("PROBE_REJECT_ABORT_PCT", "10"))


def _log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%F %T')}Z] {msg}", flush=True)


def _fetch(args) -> tuple:
    """One playbyplayv3 call. Returns (ok, seconds)."""
    gid, proxy_url = args
    from sportsdataverse.nba.nba_stats import nba_stats_playbyplayv3

    t0 = time.monotonic()
    try:
        r = nba_stats_playbyplayv3(game_id=gid, return_parsed=False, proxy_url=proxy_url)
        ok = isinstance(r, dict) and len(str(r)) > 2000
    except Exception:
        ok = False
    return ok, time.monotonic() - t0


def main() -> int:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/python")
    from nba_data_build.scrape.proxy import RoundRobin, load_proxies

    pool = load_proxies()
    if not pool:
        _log("no proxy pool -- cannot probe")
        return 1
    rr = RoundRobin(pool)
    ips = [rr.next() for _ in range(len(pool))]
    _log(f"pool has {len(ips)} IPs; ramping concurrency on playbyplayv3 (the big payload)")
    _log(f"levels={LEVELS} requests_per_level={PER_LEVEL}")

    gid_n = 1
    results = []
    for conc in LEVELS:
        # distinct game ids every level -- never re-measure a cached payload
        gids = [f"00223{str(gid_n + i).zfill(5)}" for i in range(PER_LEVEL)]
        gid_n += PER_LEVEL
        work = [(g, ips[i % len(ips)]) for i, g in enumerate(gids)]

        t0 = time.monotonic()
        with ThreadPoolExecutor(max_workers=conc) as ex:
            out = list(ex.map(_fetch, work))
        elapsed = time.monotonic() - t0

        ok = sum(1 for o, _ in out if o)
        fail = len(out) - ok
        lat = sorted(s for _, s in out)
        p50 = lat[len(lat) // 2]
        rate = len(out) / elapsed * 60
        pct_fail = fail / len(out) * 100
        results.append((conc, rate, pct_fail, p50))
        _log(
            f"  conc={conc:<3} sent={len(out)} ok={ok} rejected={fail} "
            f"({pct_fail:.0f}%) rate={rate:.0f} req/min p50_latency={p50:.1f}s"
        )
        if pct_fail >= REJECT_ABORT_PCT:
            _log(f"  ABORTING ramp -- {pct_fail:.0f}% rejected at conc={conc}")
            break

    _log("---- verdict ----")
    clean = [r for r in results if r[2] == 0]
    if not clean:
        _log("every level rejected -- something is wrong beyond rate limiting")
        return 1

    best = max(clean, key=lambda r: r[1])
    _log(f"  highest CLEAN level: conc={best[0]} at {best[1]:.0f} req/min (p50 {best[3]:.1f}s)")

    rejected = [r for r in results if r[2] > 0]
    if rejected:
        _log(
            f"  first rejection at conc={rejected[0][0]} ({rejected[0][2]:.0f}%) "
            f"-> a REAL limit sits between conc={best[0]} and conc={rejected[0][0]}"
        )
        _log(f"DECISION: cap workers at {best[0]} (the last clean level).")
    else:
        # No rejections anywhere. Did throughput still stop scaling?
        scaling = results[-1][1] / results[0][1]
        ideal = results[-1][0] / results[0][0]
        _log(
            f"  NO rejections at any level. Throughput scaled {scaling:.1f}x "
            f"across a {ideal:.0f}x concurrency increase."
        )
        if scaling < ideal * 0.5:
            _log(
                "DECISION: no rate limit found, but throughput stopped scaling -- "
                "SATURATION (proxy/host bound), not throttling. More workers will not help. "
                f"Use ~conc={best[0]}; latency, not the budget, is the wall."
            )
        else:
            _log(
                f"DECISION: no limit found up to conc={results[-1][0]} at "
                f"{results[-1][1]:.0f} req/min. The ceiling is HIGHER than probed -- "
                "worker count can go at least this high."
            )
    _log("(sequential backfill currently runs ~11 req/min -- compare against the above)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
