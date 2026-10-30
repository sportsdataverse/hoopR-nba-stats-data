"""Regenerate the injury_report fixture from the sibling raw store and the committed tree.

Run from the repo root next to ``hoopR-nba-stats-raw``::

    uv run python tests/fixtures/injury_report/make_fixture.py

Real rows, trimmed: two report versions of 2026-01-08 (the first with a NOT YET
SUBMITTED team, and the last), one Summer League version of 2026-07-15, and the
committed schedule master, player boxscores and rosters for the 2025-26 teams on
those reports.
"""

import json
from pathlib import Path

import polars as pl

HERE = Path(__file__).parent
RAW = (
    HERE.parents[2].parent / "hoopR-nba-stats-raw" / "nba_stats" / "json" / "injury_report" / "2026"
)
TREE = HERE.parents[2] / "nba_stats"
OUT_RAW, OUT_TREE = HERE / "raw" / "injury_report" / "2026", HERE / "nba_stats"


def trim(day: str, keep) -> dict:
    payload = json.loads((RAW / f"{day}.json").read_text(encoding="utf-8"))
    payload["slots"] = keep(payload["slots"])
    return payload


def first_unsubmitted(slots: list) -> list:
    return [
        next(s for s in slots if any(r.get("reason") == "NOT YET SUBMITTED" for r in s["rows"]))
    ]


OUT_RAW.mkdir(parents=True, exist_ok=True)
jan = trim("2026-01-08", lambda s: first_unsubmitted(s) + s[-1:])
jul = trim("2026-07-15", lambda s: s[-1:])
for day, payload in (("2026-01-08", jan), ("2026-07-15", jul)):
    (OUT_RAW / f"{day}.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")

teams = {r["team"] for s in jan["slots"] for r in s["rows"]}
master = pl.read_parquet(TREE / "nba_stats_schedule_master.parquet").filter(
    pl.col("season") == 2026
)
full = pl.concat_str(pl.col("home_team_city"), pl.col("home_team_name"), separator=" ")
ids = master.filter(full.is_in(list(teams))).select("home_team_id").unique()["home_team_id"]
day = pl.col("game_date_est").str.slice(0, 10)
master = master.filter(
    (day.is_in(["2026-01-08", "2026-01-09", "2026-01-29"]))
    & (pl.col("home_team_id").is_in(ids.implode()) | pl.col("away_team_id").is_in(ids.implode()))
)
(OUT_TREE / "player_boxscores" / "parquet").mkdir(parents=True, exist_ok=True)
(OUT_TREE / "rosters" / "parquet").mkdir(parents=True, exist_ok=True)
master.write_parquet(OUT_TREE / "nba_stats_schedule_master.parquet")
box = pl.read_parquet(
    TREE / "player_boxscores" / "parquet" / "player_boxscores_2026.parquet",
    columns=["team_id", "person_id", "first_name", "family_name"],
)
box.filter(pl.col("team_id").is_in(ids.implode())).unique().sort(
    "team_id", "person_id"
).write_parquet(OUT_TREE / "player_boxscores" / "parquet" / "player_boxscores_2026.parquet")
rosters = pl.read_parquet(
    TREE / "rosters" / "parquet" / "rosters_2026.parquet",
    columns=["team_id", "player_id", "player"],
)
rosters.filter(pl.col("team_id").is_in(ids.implode())).sort("team_id", "player_id").write_parquet(
    OUT_TREE / "rosters" / "parquet" / "rosters_2026.parquet"
)
print({p.name: p.stat().st_size for p in HERE.rglob("*") if p.is_file()})
