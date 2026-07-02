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

## Notes

- **`--dry-run` still compiles.** `--dry-run` scopes only the *publish* step — it plans
  the release uploads without executing them. It does **not** skip the (potentially
  multi-hour) live season compile, so it runs `build()` first. Use it to preview a
  publish of an already-built `--out` directory, not to preview the compile.
- **The validation card is left in `--out`.** `build` writes
  `nba_rapm_validation_report.md` to the output directory; it does not commit it to the
  repo. Copy it into `docs/` and commit it manually if you want it versioned, and it can
  be referenced from the release notes.
