"""Stage 08 — NBA player-impact suite (RAPM / adj-RAPM / SPM / BPM / DARKO / WAR).

Thin numbered entry over ``nba_model_publish impact``; args forward verbatim (injects the ``impact`` subcommand).
Dispatch-only BY DESIGN (rate-budgeted long build; dry_run defaults true; full-history backfills run from the droplet scripts).
Usage::

    python -m nba_model_08_impact --seasons 2026 --dry-run
    scripts/nba_models.sh 08
"""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from nba_model_publish.cli import main as _main

    argv = list(argv) if argv is not None else sys.argv[1:]
    return _main(["impact", *argv])


if __name__ == "__main__":
    raise SystemExit(main())
