# Model registry

One row per model dataset this repo publishes (Track C step 1). These are
compute-on-demand model datasets — no fitted booster artifacts; the engines
live in sdv-py and each publish writes a `*_card.json` provenance sidecar,
which is the metadata authority. `tests/test_model_registry.py` keeps this
table in lockstep.

| model | artifact(s) | release tag | training data | fitting script | gates at publish | last publish | cadence |
|---|---|---|---|---|---|---|---|
| NBA player impact (RAPM / adj-RAPM / DARKO-style engines, consolidated) | `nba_player_impact_{season}.parquet`, 30 seasons + `nba_player_impact_card.json` — **91 assets** | `nba_player_impact` | this repo's possessions/lineups trees (offline via the committed raw store; `readonly` = offline, a store miss raises) | `nba_data_build/models.py` via `nba_models.yml` (Build + publish step) | proxy-validated against the published RAPM/EPM oracle CSVs (engines beat the minutes baseline ~10%); per-run details in the card sidecar — numeric floors: TODO (not yet encoded as publish-blocking gates) | 2026-07-29 | `nba_models.yml` — dispatch-only BY DESIGN (rate-budgeted long build that must never auto-fire; `dry_run` defaults true; full-history backfills run from the droplet via `scripts/run_impact_backfill.sh`) |

Known operational notes:
- The 2026-07-28 publish was driven locally; the CI workflow existed but had
  **never run** as of the 2026-08-28 status render — treat the badge
  accordingly.
- Season dirs use the league-aware END-year convention (0.0.72 BREAKING).

## Operability (Track C steps 2–6)

- `models/manifest.yaml` — single home for the model/stage list (guarded by `tests/test_model_manifest.py`).
- One model = one numbered pipeline, flat in `python/` beside the data stages; run subsets with `scripts/nba_models.sh`.
- Compute-on-demand / enrichment surfaces: no fitted artifacts to commit, no fingerprint skip (living upstream inputs), card sidecars carry per-publish metadata.
- Engine individualization (2026-09-01): stages `nba_model_01_possessions` … `nba_model_07_darko` run ONE engine each with parquet handoffs (`build_out/impact_engines/`); `nba_model_08_impact` is the consolidated build+publish and remains the production path.
