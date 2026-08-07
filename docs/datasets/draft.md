# `draft`

NBA Stats Draft History from hoopR data repository — `drafthistory` (season-level).

| | |
|---|---|
| **Builder** | [`python/nba_stats_07_draft_creation.py`](../../python/nba_stats_07_draft_creation.py) |
| **Release tag** | [`nba_stats_draft`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_draft) |
| **File stem** | `draft_{season}.{parquet,csv,rds}` |
| **Seasons built** | — |
| **Last published** | — (newest release asset) |
| **Tag created** | — |
| **Release assets** | — |

## Automation

`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the stage-99 schedule master is restamped at the end of every run.

## Columns

_No published asset to derive a schema from yet; no model._

## Coverage

_Coverage is tracked per release asset on [`nba_stats_draft`](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nba_stats_draft)._
