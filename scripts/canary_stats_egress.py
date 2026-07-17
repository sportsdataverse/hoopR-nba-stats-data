#!/usr/bin/env python
"""Three-way stats.nba.com egress canary for the P0 droplet host (sdv-data).

stats.nba.com HANGS (does not error) on datacenter/cloud IPs, so every leg
runs under a hard wall-clock guard: no verdict within $CANARY_TIMEOUT_S
(default 45s) is reported as HANG. The probe is the same call the impact
backfill makes (``nba_stats_leaguegamelog`` via curl_cffi impersonate=chrome,
through the identical ``proxy_url`` seam), so a PASS here means the
backfill's transport works from this host.

Legs:
  direct  this host's own IP. A DigitalOcean droplet is a datacenter IP:
          expect HANG. Informational only -- never counts toward exit code.
  pb      up to $CANARY_PB_IPS (default 3) IPs from the ProxyBonanza pool
          (PROXY_ENDPOINT / PROXY_KEY / PROXY_PKG). The R daily cron has run
          stats.nba.com through this pool from GH Actions for years, so PASS
          is the expected outcome despite the pool's datacenter ASNs.
  decodo  $DECODO_PROXY_URL (residential sticky, e.g.
          ``http://user:pass@gate.decodo.com:PORT``). Skipped if unset.

Run on the droplet:
    cd python && uv run python ../scripts/canary_stats_egress.py

Exit 0 iff at least one PROXIED leg (pb / decodo) passes.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime, timezone


def _log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%F %T')}Z] {msg}", flush=True)


def _probe(proxy_url) -> None:
    """One leaguegamelog call -- the backfill's first network touch."""
    from sportsdataverse.nba import nba_stats_leaguegamelog

    payload = nba_stats_leaguegamelog(
        season=os.environ.get("CANARY_SEASON", "2023-24"),
        return_parsed=False,
        proxy_url=proxy_url,
    )
    if not isinstance(payload, dict) or "resultSets" not in payload:
        raise RuntimeError(f"unexpected payload shape: {type(payload).__name__}")


def _run_leg(name: str, proxy_url, timeout_s: float) -> str:
    """Run one probe under a wall-clock guard; return PASS / FAIL / HANG."""
    box: dict = {}

    def target():
        try:
            _probe(proxy_url)
            box["verdict"] = "PASS"
        except Exception as exc:  # noqa: BLE001 -- any error is a leg verdict, not control flow
            box["verdict"] = "FAIL"
            box["error"] = f"{type(exc).__name__}: {exc}"

    # daemon thread: a hung leg (the expected direct-leg outcome) must not block exit
    t = threading.Thread(target=target, daemon=True)
    start = time.monotonic()
    t.start()
    t.join(timeout_s)
    elapsed = time.monotonic() - start
    verdict = box.get("verdict", "HANG")
    detail = f" ({box['error']})" if "error" in box else ""
    _log(f"leg={name} verdict={verdict} elapsed={elapsed:.1f}s{detail}")
    return verdict


def main() -> int:
    timeout_s = float(os.environ.get("CANARY_TIMEOUT_S", "45"))
    _log(f"stats.nba.com egress canary (guard {timeout_s:.0f}s/leg)")
    results: dict[str, str] = {}

    _log("leg=direct probing via this host's own IP (datacenter: expect HANG)")
    results["direct"] = _run_leg("direct", None, timeout_s)

    from nba_data_build.scrape.proxy import RoundRobin, load_proxies, redact

    pool = load_proxies()
    if pool:
        n = min(int(os.environ.get("CANARY_PB_IPS", "3")), len(pool))
        _log(f"leg=pb pool has {len(pool)} IPs; probing {n}")
        nxt = RoundRobin(pool).next
        verdicts = []
        for _ in range(n):
            url = nxt()
            _log(f"leg=pb probing {redact(url)}")
            verdicts.append(_run_leg("pb", url, timeout_s))
        # one dead IP must not damn the pool; one live IP proves the egress
        results["pb"] = (
            "PASS" if "PASS" in verdicts else ("HANG" if "HANG" in verdicts else "FAIL")
        )
    else:
        _log(
            "leg=pb SKIP (PROXY_ENDPOINT/PROXY_KEY/PROXY_PKG unset or pool fetch failed)"
        )
        results["pb"] = "SKIP"

    decodo = os.environ.get("DECODO_PROXY_URL")
    if decodo:
        _log(f"leg=decodo probing {redact(decodo)} (residential sticky)")
        results["decodo"] = _run_leg("decodo", decodo, timeout_s)
    else:
        _log("leg=decodo SKIP (DECODO_PROXY_URL unset)")
        results["decodo"] = "SKIP"

    _log("---- summary ----")
    for leg, verdict in results.items():
        _log(f"  {leg:7s} {verdict}")

    ok = results["pb"] == "PASS" or results["decodo"] == "PASS"
    if results["pb"] == "PASS":
        _log(
            "DECISION: ProxyBonanza pool works -- run the backfill as-is (default proxy path)."
        )
    elif results["decodo"] == "PASS":
        _log(
            "DECISION: only residential works -- run the backfill with NO_PROXY_DIRECT=1 "
            "and https_proxy/http_proxy set to $DECODO_PROXY_URL (libcurl routes direct "
            "fetches through it). Update the LOCKED egress decision in the publication plan."
        )
    else:
        _log("DECISION: NO viable egress from this host -- do NOT launch the backfill.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
