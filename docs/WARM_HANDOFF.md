# NBA player-impact backfill — completion handoff

Written 2026-07-17 mid-run. The parallel possession-cache warm is executing on
the **sdv-data droplet (161.35.59.239)**; everything below is what remains once
it finishes. Copy-paste-runnable on the droplet.

## Where things stand

- **Merged:** `sportsdataverse-py#283` (discovery proxy fix, `f80d4909`),
  `hoopR-nba-stats-data#13/#14/#15` (runbook+canary+lock, parallel warm+probes,
  playoffs `season_type`). Main is clean.
- **Running:** `scripts/warm_possession_cache.py 2000:2024`, 5 workers, in tmux
  session `warm`. Writes the per-game cache under `/data/nba_possessions/possessions/`.
- **Real total:** 32,096 games (30,025 RS + 2,071 PO). ETA ~2.3 days from the
  write time above.

## Monitoring (already wired — no action needed)

- **On-droplet:** cron `*/10 * * * * /root/.config/sdv/warm_watch.sh`. Heartbeat
  gist `671c4f0e408554718df59869eb7bb8e4` (two files: `warm_status.txt` one-liner,
  `warm_by_season.txt` per-season table). Comments GitHub issue #16 on
  STALL/STRAY/FAILED/DIED/DONE. Removes its own cron on DONE.
- **Cloud watchdog:** routine `trig_01WWdYdiujiAwBrx2emkoHpw`, every 3h, creates a
  Google Calendar event (phone push) if the heartbeat goes stale (droplet died)
  or on DONE. Disable it after completion: https://claude.ai/code/routines

## Check progress anytime

```bash
tmux attach -t warm                                   # live (Ctrl-b d to detach)
ls /data/nba_possessions/possessions/*.parquet | wc -l   # of 32096
bash /root/.config/sdv/warm_report.sh                 # per-season table
```

## When the warm finishes (event=DONE)

### 1. Confirm the cache is complete

```bash
bash /root/.config/sdv/warm_report.sh   # every season should read "done"
ls /data/nba_possessions/*.parquet 2>/dev/null | wc -l   # MUST be 0 (no strays)
```

A season short of its total = a failed unit. Rerun the warm to fill gaps
(cached games are skipped):

```bash
cd /mnt/sdv_repos/hoopR-nba-stats-data/python && . ~/.config/sdv/env
SDV_PY_NBA_CACHE_DIR=/data/nba_possessions WARM_WORKERS=5 \
  uv run python ../scripts/warm_possession_cache.py 2000:2024
```

### 2. Sequential model build off the warm cache (CPU-only, fast)

The cache is warm, so this does no fetching — the earliest→latest prior chain
and the season-granular DARKO panel run in order, in minutes not days.

```bash
cd /mnt/sdv_repos/hoopR-nba-stats-data
. ~/.config/sdv/env
tmux new -s build
SDV_PY_NBA_CACHE_DIR=/data/nba_possessions SDV_NBA_DELAY_S=0 \
  bash scripts/run_impact_backfill.sh 2000:2024
```

Builds both season types (RS + Playoffs) — the default since #15. Watch for
`EXIT=0` and 25 parquets in `python/build_out/impact/`.

### 3. Verify the real parquet (the gate no unit test can be)

```bash
cd python && uv run python -c "
import polars as pl, glob
for f in sorted(glob.glob('build_out/impact/nba_player_impact_*.parquet')):
    df = pl.read_parquet(f)
    rs = df.filter(pl.col('season_type')=='Regular Season')
    po = df.filter(pl.col('season_type')=='Playoffs')
    dup = df.select('player_id','season','season_type').is_duplicated().sum()
    assert dup == 0, f'{f}: {dup} dupes on grain'
    # PO must be playoff-scale, not silently regular-season box logs
    if po.height:
        assert po['gp'].max() <= 30, f'{f}: PO gp max {po[\"gp\"].max()} -- season_type not reaching box logs'
    print(f.split('_')[-1], 'RS', rs.height, 'PO', po.height, 'gp_max', po['gp'].max() if po.height else '-')
print('OK: grain unique, playoffs playoff-scale')
"
```

### 4. Loader schema PR on sdv-py (needs the real footer from step 3)

`load_nba_player_impact` needs `season_type` added, and has a **pre-existing
duplicate `season`** to drop. Introspect from the real parquet, merge surgically
(a full re-introspect churns every league's column order). Code repo → branch + PR:

```bash
cd /mnt/sdv_repos/sdv-py
git switch -c fix/nba-player-impact-schema-season-type
# edit tools/codegen/schemas/loader_schemas.yaml: add season_type: Utf8, drop the 2nd `season`
uv run python tools/codegen/generate.py --docs && uv run python tools/codegen/generate.py --check
git add -A && git commit -m "fix(nba): add season_type to load_nba_player_impact, drop duplicate season"
git push -u origin fix/nba-player-impact-schema-season-type && gh pr create --base main
```

### 5. Publish the release

```bash
cd /mnt/sdv_repos/hoopR-nba-stats-data/python
uv run python -m nba_model_publish upload --dir build_out/impact --tag nba_player_impact
gh release view nba_player_impact -R sportsdataverse/sportsdataverse-data
```

This creates the `nba_player_impact` release — the one the sdv-py
release-manifest audit currently flags as an orphan (loader → dead release).
Publishing turns that check green.

### 6. Restore the R cron + install the nightly cron

The R daily scraper is **disabled** (`gh workflow list` shows `disabled_manually`).
Re-enable it — it shares the box but not, as we proved, a binding request budget:

```bash
gh workflow enable daily_nba_stats.yml -R sportsdataverse/hoopR-nba-stats-data
```

Nightly current-season refresh (cheap; the cache means only new games fetch):

```bash
crontab -e
# 09:30 UTC keeps clear of the R cron at 07:00
30 9 * * * . $HOME/.config/sdv/env && cd $HOME/hoopR-nba-stats-data && SDV_NBA_DELAY_S=2 bash scripts/run_impact_backfill.sh 2025 >> logs/impact_cron.log 2>&1
```

### 7. Tear down the monitoring

```bash
crontab -l | grep -v warm_watch.sh | crontab -    # if it didn't self-remove on DONE
# disable routine trig_01WWdYdiujiAwBrx2emkoHpw at https://claude.ai/code/routines
```

**Do NOT wipe `/data/nba_possessions`** — Phase 1.3 (`nba_play_context`) is a pure
enrichment of the same possession frame and rides this cache for nearly free.

## Facts worth carrying (measured, not assumed)

- stats.nba.com has **no detectable per-source budget** — 1,707 req/min at
  concurrency 32, zero rejections. The backfill is latency-bound, not
  request-bound. Re-run `ops/oneoff/probe_stats_ceiling.py` to re-confirm.
- The backfill is **86%... no, CPU is only 26% under parallelism — it is
  network/latency-bound per game**; parallel warm is the lever, not `delay_s`.
- **Never pass `cache_dir=` to `compile_nba_season`** — it bypasses the
  `possessions` suffix `_default_cache_dir()` adds, so the warm writes where the
  builder can't read. Check: `ls $SDV_PY_NBA_CACHE_DIR/*.parquet | wc -l` → 0.
