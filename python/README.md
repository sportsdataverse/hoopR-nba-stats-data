# nba_data_build

Local, incremental builder: compiles the missing recent NBA possession seasons
(via the sdv-py harness), fits RAPM, runs the validation card, and publishes to
`sportsdataverse-data` releases. Run from a **residential IP** (stats.nba.com
hangs on cloud IPs).

    cd python && uv sync
    # incremental (fills the gap through the current season), local only:
    uv run python -m nba_data_build --out build_out
    # then publish (uses your gh auth):
    uv run python -m nba_data_build --seasons 2023 2024 --out build_out --publish

Offline tests: `uv run pytest -q`. Live compile: `SDV_PY_NBA_STATS_LIVE=1 uv run pytest tests/test_live.py`.
