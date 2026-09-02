# Model registry

One row per model dataset this repo publishes (Track C step 1). These are
compute-on-demand model datasets — no fitted booster artifacts; the engines
live in sdv-py and each publish writes a `*_card.json` provenance sidecar,
which is the metadata authority. `tests/test_model_registry.py` keeps this
table in lockstep.

| model | artifact(s) | release tag | training data | fitting script | gates at publish | last publish | cadence |
|---|---|---|---|---|---|---|---|
| NBA player impact (RAPM / adj-RAPM / DARKO-style engines, consolidated) | `nba_player_impact_{season}.parquet`, 30 seasons + `nba_player_impact_card.json` + `nba_player_impact_spm_coefficients.json` (additive sidecar) — **91 assets published; 92 after the next publish** | `nba_player_impact` | this repo's possessions/lineups trees (offline via the committed raw store; `readonly` = offline, a store miss raises) | `nba_data_build/models.py` via `nba_models.yml` (Build + publish step) | **seven numeric floors, publish-blocking** (`nba_model_publish/gates.py`; table below) — evaluated on every `impact` invocation, report written into the card sidecar under `publish_gates` | 2026-07-29 | `nba_models.yml` — dispatch-only BY DESIGN (rate-budgeted long build that must never auto-fire; `dry_run` defaults true; full-history backfills run from the droplet via `scripts/run_impact_backfill.sh`) |

Known operational notes:
- The 2026-07-28 publish was driven locally; the CI workflow existed but had
  **never run** as of the 2026-08-28 status render — treat the badge
  accordingly.
- Season dirs use the league-aware END-year convention (0.0.72 BREAKING).

## Publish floors (`nba_model_publish/gates.py`)

Every floor sits strictly BELOW the value observed on the 2026-07-29 published
release across all 30 seasons (1997–2026), measured 2026-09-01 with

```sh
python -m nba_model_publish gates --from-release   --oracle-dir "$SDV_PY_NBA_ORACLE_DIR" --json-out gates.json
```

A floor is a regression detector, not a target: **never lower one to make a
publish pass** — debug the build, and a re-derivation must record the new
observation beside the constant.

| gate | floor | observed (min across seasons) | what it catches |
|---|---:|---:|---|
| `rs_rows_min` | 400 | 428 (2003) | a season that silently lost its population |
| `r_rapm_adj_min` | 0.75 | 0.806 (2013) | the SPM prior overwriting RAPM instead of shrinking it |
| `r_spm_rapm_min` | 0.22 | 0.264 (1999) | SPM no longer fitting the target it was trained on |
| `r_rapm_yoy_min` | 0.24 | 0.289 (2020→2021) | the panel losing player-level persistence |
| `r_darko_fwd_min` | 0.20 | 0.242 (2020) | the projection decoupling from next-season RAPM |
| `oracle_rapm_r_min` | 0.90 | 0.948 (2014) | concurrent validity vs published Ryan Davis RAPM |
| `oracle_rapm_beat_minutes_min` | 0.50 | +0.602 (2015) | RAPM beating the minutes-played baseline |

The oracle pair runs only when `SDV_PY_NBA_ORACLE_DIR` (or `--oracle-dir`)
holds the published CSVs; absent, they report **SKIPPED — which is not PASS**.
The 14 oracle-covered seasons (2010–2023) show `r` 0.948–0.990 against Ryan
Davis single-season RAPM, beating the minutes baseline by **+0.60 to +0.75
correlation points** — the registry previously recorded this as "~10%", which
understated the measured margin. Dunks & Threes EPM is recorded in the report
but NOT gated: two covered seasons (2025–26, `r` 0.636/0.659 vs a minutes
baseline of 0.620/0.622) are too thin to set a floor from, and EPM's own
minutes dependence makes the margin uninformative.

## Operability (Track C steps 2–6)

- `models/manifest.yaml` — single home for the model/stage list (guarded by `tests/test_model_manifest.py`).
- One model = one numbered pipeline, flat in `python/` beside the data stages; run subsets with `scripts/nba_models.sh`.
- Compute-on-demand / enrichment surfaces: no fitted artifacts to commit, no fingerprint skip (living upstream inputs), card sidecars carry per-publish metadata.
- Additive artifact (2026-09-01): `nba_player_impact_spm_coefficients.json` — one record per season with the fitted offense/defense SPM coefficient vectors, feature names, the fit population's feature SDs, and the train-time fit metrics. Written by the build; rebuildable from published seasons + the committed raw store with `python -m nba_model_publish spm-coefficients --seasons 1997:2026 --raw-store-dir <hoopR-nba-stats-raw> --out docs/models`.
- Engine individualization (2026-09-01): stages `nba_model_01_possessions` … `nba_model_07_darko` run ONE engine each with parquet handoffs (`build_out/impact_engines/`); `nba_model_08_impact` is the consolidated build+publish and remains the production path.
