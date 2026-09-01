"""Stage 06 — WAR engine (RAPM rating x pts_per_win from stage 03).

Thin numbered pipeline for ONE engine of the player-impact suite; compute +
handoff semantics live in ``nba_model_publish.impact_stages`` (parquet
handoffs under build_out/impact_engines). The consolidated build+publish is
stage 08 (``nba_model_08_impact``). Single home: models/manifest.yaml.

Usage::

    python -m nba_model_06_war --seasons 2023 2024 
    scripts/nba_models.sh 06
"""
from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    from nba_model_publish import impact_stages as S

    ap = argparse.ArgumentParser(prog="python -m nba_model_06_war")
    ap.add_argument("--seasons", nargs="+", required=True, metavar="ENDYEAR",
                    help="END years (2024 = 2023-24); two values = inclusive range")
    ap.add_argument("--engines-dir", default=S.DEFAULT_ENGINES_DIR)
    ap.add_argument("--season-types", default="Regular Season,Playoffs",
                    metavar="CSV")
    ap.add_argument("--replacement-level", type=float, default=-2.0)
    a = ap.parse_args(argv)
    n = S.run_war(S.parse_seasons(a.seasons), season_types=S.parse_season_types(a.season_types), engines_dir=a.engines_dir, replacement_level=a.replacement_level)
    print(f"[war] wrote {n} artifact group(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
