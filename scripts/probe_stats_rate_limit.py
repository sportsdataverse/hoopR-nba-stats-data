#!/usr/bin/env python
"""Measure the REAL stats.nba.com rate limit from this host, per-IP vs per-source.

The repo pins ``SDV_NBA_DELAY_S=7`` from one number in CLAUDE.md: "empirically
~200-300 req / 10 min of *any* type", treated as a **per-source** budget. The R
side rate-limits globally at 250/10min even though it rotates the proxy pool.

That number predates nothing we can check, and the distinction is worth ~50h of
wall clock on the 25-season backfill:

  * per-SOURCE limit -> rotation buys nothing; delay 7 is correct; backfill ~61h.
  * per-IP limit     -> 50 IPs multiply the ceiling; delay ~1 is safe; backfill ~10h.

Three phases, each bounded and abortable:

  1. baseline   few requests, slow, one IP        -- proves the transport works
  2. single-IP  many requests, fast, ONE IP       -- finds the PER-IP ceiling
  3. rotated    many requests, fast, MANY IPs     -- tests for a PER-SOURCE ceiling
                aggregate rate deliberately exceeds the folk budget

Failure signature: stats.nba.com does NOT error -- ``_get`` maps a non-200/blank
body to ``{}``. An empty dict IS the rejection. Never read "no exception" as
success.

Run (R cron should be disabled first so nothing else shares the budget):
    cd python && uv run python ../scripts/probe_stats_rate_limit.py
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

# A real per-game endpoint, like the backfill's actual load. Small payload.
GAME_ID = os.environ.get("PROBE_GAME_ID", "0022300061")

# Bounds -- a runaway probe would poison the pool for the backfill that follows.
P2_N = int(os.environ.get("PROBE_P2_N", "40"))  # single-IP burst
P2_DELAY = float(os.environ.get("PROBE_P2_DELAY", "0.3"))
P3_N = int(os.environ.get("PROBE_P3_N", "300"))  # rotated burst
P3_DELAY = float(os.environ.get("PROBE_P3_DELAY", "0.2"))
ABORT_STREAK = int(os.environ.get("PROBE_ABORT_STREAK", "8"))


def _log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%F %T')}Z] {msg}", flush=True)


def _hit(proxy_url: str) -> bool:
    """One boxscore fetch. True iff a real payload came back.

    An empty dict is stats.nba.com's rejection, not an error -- treat it as a
    failed request, not a passed one.
    """
    from sportsdataverse.nba.nba_stats import nba_stats_boxscoretraditionalv3

    try:
        r = nba_stats_boxscoretraditionalv3(
            game_id=GAME_ID, return_parsed=False, proxy_url=proxy_url
        )
        return isinstance(r, dict) and "boxScoreTraditional" in str(r)[:400]
    except Exception:
        return False


def _burst(name: str, urls: list, n: int, delay: float) -> dict:
    """Fire *n* requests, one per url (cycled), sleeping *delay* between.

    Aborts early on a sustained failure streak so a real limit costs us the
    streak, not the whole budget.
    """
    ok = fail = streak = 0
    t0 = time.monotonic()
    first_fail_at = None
    for i in range(n):
        if _hit(urls[i % len(urls)]):
            ok += 1
            streak = 0
        else:
            fail += 1
            streak += 1
            if first_fail_at is None:
                first_fail_at = i + 1
            if streak >= ABORT_STREAK:
                _log(f"  {name}: ABORTING -- {streak} consecutive rejections")
                break
        if delay:
            time.sleep(delay)
    elapsed = time.monotonic() - t0
    sent = ok + fail
    rate = sent / elapsed * 60 if elapsed else 0
    _log(
        f"  {name}: sent={sent} ok={ok} rejected={fail} "
        f"elapsed={elapsed:.0f}s rate={rate:.0f} req/min "
        f"first_rejection_at={first_fail_at or 'none'}"
    )
    return {"sent": sent, "ok": ok, "fail": fail, "rate": rate, "first_fail": first_fail_at}


def main() -> int:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/python")
    from nba_data_build.scrape.proxy import RoundRobin, load_proxies

    pool = load_proxies()
    if not pool:
        _log("no proxy pool (PROXY_ENDPOINT/_KEY/_PKG unset?) -- cannot probe")
        return 1
    rr = RoundRobin(pool)
    urls = [rr.next() for _ in range(len(pool))]
    _log(f"pool has {len(urls)} IPs; probing game_id={GAME_ID}")
    _log("folk budget under test: ~250 req/10min = ~25 req/min, per SOURCE")

    _log("phase 1: baseline -- 5 requests, one IP, 2s apart")
    p1 = _burst("baseline", urls[:1], 5, 2.0)
    if p1["ok"] == 0:
        _log("BASELINE FAILED -- egress is broken; nothing else is meaningful")
        return 1

    _log(f"phase 2: single-IP burst -- {P2_N} requests, ONE IP, {P2_DELAY}s apart")
    _log("  (if the limit is PER-IP, this is where it shows up)")
    p2 = _burst("single-ip", urls[1:2], P2_N, P2_DELAY)

    _log(f"phase 3: rotated burst -- {P3_N} requests across {len(urls)} IPs, {P3_DELAY}s apart")
    _log("  (aggregate rate deliberately exceeds the folk per-source budget)")
    p3 = _burst("rotated", urls, P3_N, P3_DELAY)

    _log("---- verdict ----")
    per_ip_clean = p2["fail"] == 0
    rotated_clean = p3["fail"] == 0
    _log(f"  single-IP  {p2['ok']}/{p2['sent']} ok at {p2['rate']:.0f} req/min on ONE ip")
    _log(f"  rotated    {p3['ok']}/{p3['sent']} ok at {p3['rate']:.0f} req/min aggregate")

    if rotated_clean and p3["rate"] > 60:
        _log(
            f"DECISION: {p3['sent']} requests at {p3['rate']:.0f} req/min aggregate with ZERO "
            "rejections. That is far above the ~25 req/min per-source folk budget, so the "
            "budget is NOT per-source at this scale -- rotation multiplies the ceiling. "
            "delay_s can drop well below 7."
        )
    elif per_ip_clean and not rotated_clean:
        _log(
            "DECISION: single-IP clean but rotated rejected -- a SOURCE-level limit is real. "
            "Rotation does not help. Keep delay_s=7."
        )
    elif not per_ip_clean:
        _log(
            f"DECISION: a PER-IP limit exists (first rejection at request "
            f"{p2['first_fail']} on one ip). Pace per-IP, not globally: with "
            f"{len(urls)} IPs the safe aggregate is roughly {len(urls)}x the per-IP rate."
        )
    else:
        _log("DECISION: inconclusive -- widen the probe before re-pacing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
