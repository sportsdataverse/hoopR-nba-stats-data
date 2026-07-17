# nba_player_impact — playoffs as a season_type dimension

**Date:** 2026-07-17
**Status:** approved, not yet implemented
**Scope:** `python/nba_model_publish/builders.py`, `cli.py`, `sdv-py` loader schema

## Problem

`build_nba_player_impact` calls `compile_nba_season(season, ...)` without
`season_type`, so it silently takes the `"Regular Season"` default. Every
`nba_player_impact` figure is regular-season-only **and unlabeled** — nothing in
the output says so. Playoffs are absent entirely.

The dataset has never been published (the `nba_player_impact` release does not
exist; it is the orphan tag in the repo's release-manifest audit), so the grain
can be defined correctly now with no backward-compatibility burden.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Grain becomes `(player_id, season, season_type)`; values `"Regular Season"` / `"Playoffs"` | Playoff performance is separable. Mirrors the `leaguedash` precedent (`SEASON_TYPES` in `nba_data_build/scrape/leaguedash.py`), which stacks both and tags rows. |
| 2 | Scope is RS + Playoffs. **PlayIn excluded**, documented in the model card | The API exposes `PlayIn` as a third `SeasonType` (2020+). It is ~4–6 games/year, exists only from 2020, and RAPM on that sample is meaningless. Folding it into `Playoffs` would misstate provenance. Excluding it silently would repeat the discovery-gap failure — hence the explicit model-card note. |
| 3 | SPM `coef` and `pts_per_win` are **fitted once on the season's RS** and reused for PO | Both are fitted from season data. A playoff sample is ~15 games/team; re-fitting trains noise on noise, and SPM coefficients in particular would be unstable year to year. Inheriting also keeps PO and RS numbers on the same scale, so they are comparable. `nba_bpm` is unaffected — BPM 2.0's coefficients are fixed constants from the published methodology, so it is a formula applied to whichever logs it receives. |
| 4 | adj-RAPM prior carries forward as a **possession-weighted RS+PO blend** | Playoff form propagates without a ~15-game sample overriding a 1230-game one. Pure chronological chaining (`prev_spm` = PO SPM) would make each season's RS prior a thin playoff estimate — adding playoffs would *degrade* every RS row versus today. Within a season the PO fit still takes the RS estimate as its prior, which is what makes the thin playoff sample usable at all. |
| 5 | DARKO panel keeps **one row per player-season**; rating = RS+PO possession-weighted blend. Both output rows carry that season's projection | DARKO is structurally season-granular: its aging curve maps age→rating change per season, `q` is fit as per-season drift, and the builder filters `last_season == season`. A chronological RS→PO panel would double-apply aging, mis-scale `q`, and match two rows per season. Blending preserves the time axis while letting playoff form move the projection. DARKO projects *next season*, which is not a playoff-specific quantity, so repeating the value is honest. |

Decisions 4 and 5 use the **same** possession-weighted blending rule — one rule
for both forward-carrying mechanisms.

## What does not change

- **No SDK work.** `compile_nba_season(season, season_type=...)` and
  `nba_box_logs(season, season_type=...)` already accept the parameter; the
  builder simply never passed it.
- **The possession cache stays valid.** Playoff game ids are `004…`; regular
  season are `002…`. Distinct keys, no collision, `PIPELINE_VERSION` unchanged.
  The in-flight RS smoke's cache is reused as-is; playoffs only add files.
- **`nba_bpm`** — formula, not a fit (see decision 3).

## Structure

Per season, the builder loop becomes:

```
RS:  poss_rs  = compile_nba_season(season, season_type="Regular Season")
     rapm_rs  = nba_rapm(poss_rs)
     logs_rs  = nba_box_logs(s_str, season_type="Regular Season")
     coef     = train_spm(box_features(logs_rs), rapm_rs)      # fitted ONCE
     ppw      = calibrate_pts_per_win(team_season(logs_rs))    # fitted ONCE
     adj_rs   = nba_adj_rapm(poss_rs, prior=carry)             # carry from prev season
     -> emit row(season_type="Regular Season")

PO:  poss_po  = compile_nba_season(season, season_type="Playoffs")
     (skip cleanly if empty — a lockout/incomplete season has no playoffs)
     rapm_po  = nba_rapm(poss_po)
     logs_po  = nba_box_logs(s_str, season_type="Playoffs")
     spm_po   = nba_spm(box_features(logs_po), coef)           # RS coef reused
     adj_po   = nba_adj_rapm(poss_po, prior=AdjRapmModel.from_spm(spm_rs).prior)
     war_po   = nba_war(rapm_po, poss_po, pts_per_win=ppw)     # RS ppw reused
     -> emit row(season_type="Playoffs")

carry        = poss_weighted_blend(spm_rs, spm_po)             # -> next season's prior
panel_row    = poss_weighted_blend(rapm_rs, rapm_po)           # one row per player-season
```

`nba_darko` is then called on the season-granular panel exactly as today, and
both emitted rows join the same `darko_*` values for that season.

## Interfaces

- **`build_nba_player_impact`** gains no new required args. It always builds both
  season types.
- **CLI** gains `--season-types` (default `"Regular Season,Playoffs"`) so a run
  can be narrowed without a code change — same env-only-tuning principle as
  `--delay-s`.
- **Output** gains a `season_type: Utf8` column.

## Schema changes (`sdv-py`)

`tools/codegen/schemas/loader_schemas.yaml` → `load_nba_player_impact`:

1. **Add** `season_type` (`Utf8`).
2. **Fix** the duplicate `season` entry — `season` is currently declared twice
   (a pre-existing bug, unrelated to playoffs, found while reading the schema).

Re-introspect from the real parquet footer per the runbook, and **merge
surgically** — a full re-introspect churns every league's column order.

## Error handling

- **A season with no playoffs** (e.g. a lockout-shortened or in-progress season)
  yields an empty PO frame: emit the RS row, skip the PO row, and let `carry`
  fall back to the RS SPM alone. Do not treat it as an error.
- **Do not** let an empty PO frame silently zero out the season. The empty-in/
  empty-out contract is why the unproxied-discovery bug exited 0 with no data;
  an explicit `poss_po.height == 0` branch with a logged reason keeps that
  distinguishable from a network failure.
- The existing `assert rapm.height > 0` guard stays on the RS path.

## Testing

- **Grain:** a two-season build emits exactly 2 rows per player-season present in
  both types, with distinct `season_type` values.
- **Inheritance:** the SPM coef and `pts_per_win` used for PO are byte-identical
  to the RS-fitted ones (assert the PO call receives the RS values, mirroring
  how the proxy tests assert the URL reaches the fetcher — a stub must mirror
  the real signature, not a convenient one).
- **Blend:** `carry` and the DARKO panel row equal the possession-weighted
  combination of the RS and PO inputs; with an empty PO frame both fall back to
  the RS values exactly.
- **No-playoffs season:** emits the RS row only, no exception, and does not break
  the prior chain.
- **Regression:** an RS-only build (`--season-types "Regular Season"`) reproduces
  today's numbers, so the change is diffable against the current behavior.

## Budget impact

~85 playoff games/season × 25 seasons ≈ **+2,125 games (~+7%)** → ~99K requests
against the shared ~250 req/10min budget ⇒ ~65h floor. Unchanged 2.5–3 day
envelope at `SDV_NBA_DELAY_S=7`.

## Open / follow-ups

- `wehoop-wnba-stats-data` repeats this at `stats.wnba.com` and will need the
  same treatment; the WNBA postseason format differs and is not specified here.
- The runbook's success check is `grep "EXIT=" | tail -1`, which passes on an
  empty run. A games-discovered floor assertion would catch a silent no-op
  backfill; tracked separately from this design.
