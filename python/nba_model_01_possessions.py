"""Stage 01 — possession compile per season/type.

Thin numbered pipeline for ONE engine of the player-impact suite; compute +
handoff semantics live in ``nba_model_publish.impact_stages`` (parquet
handoffs under build_out/impact_engines). The consolidated build+publish is
stage 08 (``nba_model_08_impact``). Single home: models/manifest.yaml.

Usage::

    python -m nba_model_01_possessions --seasons 2023 2024 [--raw-store-dir ...]
    scripts/nba_models.sh 01
"""
from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    from nba_model_publish import impact_stages as S

    ap = argparse.ArgumentParser(prog="python -m nba_model_01_possessions")
    ap.add_argument("--seasons", nargs="+", required=True, metavar="ENDYEAR",
                    help="END years (2024 = 2023-24); two values = inclusive range")
    ap.add_argument("--engines-dir", default=S.DEFAULT_ENGINES_DIR)
    ap.add_argument("--season-types", default="Regular Season,Playoffs",
                    metavar="CSV")
    ap.add_argument("--lineup-source", default="auto")
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--delay-s", type=float, default=0.6)
    ap.add_argument("--raw-store-dir", default=None,
                    help="committed -raw JSON store (dir or URL); direct fetch otherwise")
    a = ap.parse_args(argv)
    n = S.run_possessions(S.parse_seasons(a.seasons), season_types=S.parse_season_types(a.season_types), engines_dir=a.engines_dir, lineup_source=a.lineup_source, cache_dir=a.cache_dir, delay_s=a.delay_s, raw_store_dir=a.raw_store_dir)
    print(f"[possessions] wrote {n} artifact group(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
