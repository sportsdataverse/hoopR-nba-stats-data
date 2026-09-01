# NBA player impact — model documentation

Consolidated per-season player-impact suite published to `nba_player_impact`
(per-season parquet/csv/rds + a `nba_player_impact_card.json` provenance
sidecar on every publish — the card is the per-run metadata authority).

## Engines (columns by family)

| engine | what it contributes |
|---|---|
| RAPM | possession on/off ridge (o_rapm / d_rapm / rapm) |
| adj-RAPM | RAPM with an SPM-derived prior (previous season's RS+PO blend) |
| SPM | box-score plus/minus, coefficients fit on RS RAPM targets |
| BPM 2.0 | box logs + listed positions |
| DARKO-style | cross-season Kalman filter + aging curve (projects next season) |
| WAR | RAPM rating x calibrated pts-per-win, replacement level -2.0 |

Substrates: the committed `hoopR`-stats raw store (possessions
compile + leaguegamelog / playerindex / leaguedashplayerbiostats captures) —
offline and clone-free via the URL store backend.

## Pipeline

Per-engine numbered stages `nba_model_01_possessions` … `nba_model_07_darko`
(parquet handoffs under `build_out/impact_engines/`; hermetic stub tests cover
the chain including cross-season prior threading) with the consolidated
build+publish as `nba_model_08_impact`. Retrain is dispatch-only BY DESIGN
(rate-budgeted long build; `dry_run` defaults true). Full-history backfills run from the droplet (`scripts/run_impact_backfill.sh` after `scripts/hydrate_raw_store.sh`); the per-file URL store backend suits a refresh, not a backfill.

## Results / validation

Proxy-validated against the published RAPM/EPM oracle CSVs: the engines beat
the minutes-played baseline by ~10% on the proxy tasks; per-run diagnostics
live in the release card sidecar. Numeric publish-blocking floors are a
recorded TODO in `models/REGISTRY.md` (stated, not yet encoded).

## Figures

None committed yet — engine-level diagnostic figures are a recorded follow-up;
the release card carries the per-run numbers in the meantime.
