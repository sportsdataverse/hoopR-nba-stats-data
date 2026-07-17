# P0 droplet runbook — NBA player-impact backfill host

Stands up the **sdv-data droplet (161.35.59.239)** as the stats.nba.com refresh
host and runs the one-time `nba_player_impact` backfill (publication-plan Phase
1.1, spec steps 3–6). Everything here is copy-paste-runnable by a human on the
droplet — no assistant in the loop.

Why a droplet at all: stats.nba.com **hangs (never errors) on datacenter/cloud
IPs**, and the full backfill needs ~92K requests against a shared ~250 req/10min
budget — a multi-day resumable run that no 6h-capped GH Actions job can host.

```
sequence:  1. setup (once)  →  2. egress canary  →  3. smoke (1 season, dry-run)
           →  4. full backfill 2000:2024  →  5. verify + loader re-introspect
           →  6. nightly cron
```

---

## 1. One-time setup

```bash
# on 161.35.59.239
sudo apt-get update && sudo apt-get install -y git curl gh tmux
#   gh = GitHub CLI — nba_data_build/publish.py shells out to `gh release upload`.
#   If apt has no gh package, follow https://cli.github.com installation docs.
curl -LsSf https://astral.sh/uv/install.sh | sh && . ~/.profile

git clone https://github.com/sportsdataverse/hoopR-nba-stats-data.git ~/hoopR-nba-stats-data
cd ~/hoopR-nba-stats-data/python && uv sync   # installs sportsdataverse@main, curl_cffi, ...

# secrets — one env file, sourced by your shell AND by cron. chmod 600, never commit.
mkdir -p ~/.config/sdv && chmod 700 ~/.config/sdv
cat > ~/.config/sdv/env <<'EOF'
export PROXY_ENDPOINT=   # ProxyBonanza API endpoint (same three the R cron uses)
export PROXY_KEY=
export PROXY_PKG=
export DECODO_PROXY_URL= # optional residential sticky: http://user:pass@gate.decodo.com:PORT
export GH_TOKEN=         # token with repo scope on sportsdataverse-data (release uploads)
EOF
chmod 600 ~/.config/sdv/env && . ~/.config/sdv/env
gh auth status >/dev/null 2>&1 || echo "$GH_TOKEN" | gh auth login --with-token

# possession cache — the resume checkpoint. Wants ~5–10 GB free.
sudo mkdir -p /data/nba_possessions && sudo chown "$USER" /data/nba_possessions \
  || { mkdir -p "$HOME/nba_possessions"; echo 'export SDV_PY_NBA_CACHE_DIR=$HOME/nba_possessions' >> ~/.config/sdv/env; }
df -h /data 2>/dev/null || df -h "$HOME"
```

## 2. Egress canary — decides the proxy question (~3 min)

```bash
. ~/.config/sdv/env
cd ~/hoopR-nba-stats-data/python && uv run python ../scripts/canary_stats_egress.py
```

Probes the exact call the backfill makes, three ways, each under a 45s hang
guard (`CANARY_TIMEOUT_S` to change). Expected: `direct=HANG` (droplet IP is
datacenter), `pb=PASS` (the R daily cron has used this pool against
stats.nba.com from GH Actions for years — the 07-16 "ProxyBonanza is
datacenter" finding was fatal for **NCAA's Akamai**, a different blocker).

| canary outcome | action |
|---|---|
| `pb=PASS` | Run the backfill as-is (default proxy path). LOCKED decision stands. |
| `pb` fails, `decodo=PASS` | Run with `NO_PROXY_DIRECT=1` **and** `export https_proxy=$DECODO_PROXY_URL http_proxy=$DECODO_PROXY_URL` (libcurl routes the direct fetches through it). Update the LOCKED egress decision in `ClaudeCowork/notes/2026-07-12-model-dataset-publication-plan.md`. |
| all proxied legs fail | **Stop.** No viable egress — fix the proxy story before any backfill. |

## 3. Smoke — one season, no upload (~8–10 h at delay 7)

```bash
. ~/.config/sdv/env
cd ~/hoopR-nba-stats-data
tmux new -s smoke
SDV_NBA_DELAY_S=7 bash scripts/run_impact_backfill.sh 2023 --dry-run
```

Watch from any other shell (exact path printed at launch):

```bash
tail -f ~/hoopR-nba-stats-data/logs/impact_backfill_*.log
```

A stalled timestamp = a hang (egress died); Ctrl-C and rerun — the per-game
cache skips everything already compiled. The 2023 cache seeded here is
**reused** by the full backfill, so nothing is wasted. Success looks like
`nba_player_impact_2023.parquet` + a card in `python/build_out/impact/` and
`EXIT=0` as the log's last line.

**Do not publish a standalone mid-range season**: seasons build
earliest→latest so the adj-RAPM prior and DARKO panel flow forward — an
out-of-sequence single-season build has no prior chain. `--dry-run` on the
smoke is what makes it safe.

## 4. Full backfill 2000:2024 (~2.5–3 days, resumable)

Budget math: ~1,230 games/season × 25 seasons × 3 endpoints ≈ **92K requests**
against the shared ~250 req/10min budget ⇒ ~61 h floor. `SDV_NBA_DELAY_S=7`
(≈26 req/min) paces right at budget. The default `0.6` **will blow the shared
budget** — it's fine only for small cached re-runs.

The budget is shared with the R daily scraper (`daily_nba_stats.yml`, 07:00
UTC, July window active). Disable it for the duration:

```bash
gh workflow disable daily_nba_stats.yml -R sportsdataverse/hoopR-nba-stats-data
```

Launch (in tmux — this outlives your SSH session):

```bash
. ~/.config/sdv/env
cd ~/hoopR-nba-stats-data
tmux new -s backfill
SDV_NBA_DELAY_S=7 bash scripts/run_impact_backfill.sh 2000:2024
```

- **Watch:** `tail -f ~/hoopR-nba-stats-data/logs/impact_backfill_*.log`
- **Pause/resume:** Ctrl-C anytime; rerun the same command. Cached games are
  skipped — only the remainder refetches.
- **Re-tune pace mid-run:** Ctrl-C, change `SDV_NBA_DELAY_S`, rerun. Env-only,
  no code changes.
- **Died after build, before upload?** The upload runs once at the end. Recover
  without recomputing:
  `cd python && uv run python -m nba_model_publish upload --dir build_out/impact --tag nba_player_impact`

Re-enable the R cron when done:

```bash
gh workflow enable daily_nba_stats.yml -R sportsdataverse/hoopR-nba-stats-data
```

## 5. Verify + downstream

```bash
ls python/build_out/impact/          # expect 25 season parquets + model card
grep "EXIT=" logs/impact_backfill_*.log | tail -1   # EXIT=0
gh release view nba_player_impact -R sportsdataverse/sportsdataverse-data
```

Then on the dev box (sdv-py):

1. Re-introspect the loader schema from the real parquet footer:
   `uv run python tools/codegen/generate.py --loader-schemas` — **merge
   surgically** (a full re-introspect churns every league's column order).
2. Round-trip: `load_nba_player_impact(source="sdv")` for one season.
3. **Do not wipe `/data/nba_possessions`** — Phase 1.3 (`nba_play_context`) is
   a pure enrichment of the same possession frame and rides this cache for
   nearly free.

## 6. Nightly cron (current season)

Cheap after the backfill — the cache means only new games fetch. 09:30 UTC
keeps clear of the R cron at 07:00.

```bash
crontab -e
# m  h  dom mon dow
30 9 * * * . $HOME/.config/sdv/env && cd $HOME/hoopR-nba-stats-data && SDV_NBA_DELAY_S=2 bash scripts/run_impact_backfill.sh 2025 >> logs/impact_cron.log 2>&1
```

Season arg = start year (`2025` = 2025-26); bump it each October. Check
`logs/impact_cron.log` for `EXIT=0` after the first scheduled run.

## Gotchas

- stats.nba.com **hangs, never errors** — a stalled log timestamp IS the
  failure signal. The CLI refuses to start with an empty proxy pool for
  exactly this reason; `--no-proxy` (`NO_PROXY_DIRECT=1`) is the explicit
  opt-out.
- **One process, sequential** — never parallelize the fetch loop; the budget
  is per-source, not per-process, and parallel workers blow it (the R side
  removed its `furrr` path for the same reason).
- The proxy env trio is the same `PROXY_ENDPOINT`/`PROXY_KEY`/`PROXY_PKG` the
  R workflows use (GitHub secrets) — never commit them, never echo them.
- WNBA repeats this runbook later via `wehoop-wnba-stats-data`
  (stats.wnba.com, same cloud-IP block) — out of scope here.
