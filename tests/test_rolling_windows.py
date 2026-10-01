"""Stage 17 ``rolling_windows`` (F3b-T2): rolling shooting form over the committed tree.

sdv-py's ``shot_events`` + ``rolling_windows`` over every committed shots season up
to the one built, dated by the committed schedule master. The archive tests run on
two real committed seasons copied to a tmp tree; the oracle is a hand count of
Stephen Curry's 2023-24 + 2024-25 attempts (the same count sdv-py #657 pins).
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from nba_data_build import docs
from nba_data_build.models import MODELS, polars_schema
from nba_data_build.reshape import build, cli, datasets
from polars.testing import assert_frame_equal
from sportsdataverse.rolling_windows import OUTPUT_SCHEMA, rolling_windows, shot_events

REPO = Path(__file__).resolve().parents[1]
TREE = REPO / "nba_stats"
MASTER = "nba_stats_schedule_master.parquet"
CURRY = "201939"

#: Reads the committed nba_stats/ tree, which PR CI does not check out.
real = pytest.mark.archive

# Curry's first four attempts of 0022400007 (2024-11-12), verbatim from the
# committed nba_stats/shots/parquet/shots_2025.parquet.
FOUR = pl.DataFrame(
    {
        "game_id": ["0022400007"] * 4,
        "season": pl.Series([2025] * 4, dtype=pl.Int32),
        "season_type_id": ["2"] * 4,
        "period": [1] * 4,
        "clock": ["PT11M28.00S", "PT09M14.00S", "PT09M00.00S", "PT06M22.00S"],
        "team_id": [1610612744] * 4,
        "person_id": [201939] * 4,
        "player_name": ["Curry"] * 4,
        "shot_result": ["Made", "Made", "Missed", "Made"],
        "shot_value": [3, 2, 3, 3],
    }
)
FOUR_MASTER = pl.DataFrame({"game_id": ["0022400007"], "game_date_est": ["2024-11-12T00:00:00Z"]})


def _row(df: pl.DataFrame, **kw) -> dict:
    out = df.filter(pl.all_horizontal([pl.col(k) == v for k, v in kw.items()]))
    assert out.height == 1, out
    return out.row(0, named=True)


@pytest.fixture
def four_tree(tmp_path: Path) -> Path:
    base = tmp_path / "nba_stats"
    (base / "shots" / "parquet").mkdir(parents=True)
    FOUR.write_parquet(base / "shots" / "parquet" / "shots_2025.parquet")
    FOUR_MASTER.write_parquet(base / MASTER)
    return base


def test_four_real_attempts_window_into_one_short_row(four_tree):
    df = build.build_rolling_windows(four_tree, 2025)
    assert dict(df.schema) == {**OUTPUT_SCHEMA, "id_source": pl.Utf8}
    assert set(df["season"]) == {2025}, "END year in, END year out: no START offset"
    assert set(df["id_source"]) == {"nba_stats"}
    r = _row(df, window_unit="fg3a", window_n=50)
    assert r["n"] == 3 and abs(r["cur"] - 2 / 3) < 1e-12
    assert r["prev"] is None and r["delta_prev_rank"] is None and r["qualified"] is False
    assert r["entity_id"] == CURRY and r["team_id"] == "1610612744"
    assert r["last_event_date"] == date(2024, 11, 12)
    assert _row(df, window_unit="fga", window_n=50)["cur"] == 0.75


def test_missing_season_returns_the_contract_schema(four_tree):
    empty = build.build_rolling_windows(four_tree, 2026)
    assert empty.height == 0 and dict(empty.schema) == {**OUTPUT_SCHEMA, "id_source": pl.Utf8}


def test_cli_reuses_this_runs_shots_and_falls_back_to_the_tree(four_tree):
    """The daily run builds shots first and must not read yesterday's committed file."""
    (four_tree / "shots" / "parquet" / "shots_2025.parquet").unlink()
    ds = datasets.BY_KEY["rolling_windows"]
    assert cli.build_dataset("root", ds, 2025, _shots=FOUR, base=four_tree).height > 0
    assert cli.build_dataset("root", ds, 2025, base=four_tree).height == 0


def test_stage_17_is_registered_everywhere():
    ds = datasets.BY_KEY["rolling_windows"]
    assert (ds.stem, ds.release_tag, ds.level, ds.endpoint) == (
        "rolling_windows",
        "nba_stats_rolling_windows",
        "derived",
        None,
    )
    keys = [d.key for d in datasets.DATASETS]
    assert keys.index("rolling_windows") == keys.index("metric_curves") - 1, "17 builds before 18"
    assert keys.index("shots") < keys.index("rolling_windows"), "derives from this run's shots"
    notes = datasets.RELEASE_NOTES["nba_stats_rolling_windows"]
    for phrase in ("season_type_id", "id_source", "END", "career_baseline", "1997"):
        assert phrase in notes
    assert docs.BUILDER["rolling_windows"] == "python/nba_stats_17_rolling_windows_creation.py"
    assert polars_schema("rolling_windows") == pl.Schema({**OUTPUT_SCHEMA, "id_source": pl.Utf8})
    assert "rolling_windows" in MODELS


@pytest.fixture(scope="module")
def two_seasons(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The committed 2024 + 2025 shots and the schedule master, copied to a tmp tree."""
    src = [TREE / "shots" / "parquet" / f"shots_{y}.parquet" for y in (2024, 2025)]
    if not all(p.is_file() for p in src) or not (TREE / MASTER).is_file():
        pytest.skip("no committed shots / schedule master")
    base = tmp_path_factory.mktemp("tree") / "nba_stats"
    (base / "shots" / "parquet").mkdir(parents=True)
    for p in src:
        shutil.copy(p, base / "shots" / "parquet" / p.name)
    shutil.copy(TREE / MASTER, base / MASTER)
    return base


@pytest.fixture(scope="module")
def rw2025(two_seasons: Path) -> pl.DataFrame:
    return build.build_rolling_windows(two_seasons, 2025)


# hand count (plain Python, sdv-py #657's fixture README): Curry's regular-season +
# playoff attempts ordered by (date, game, period, clock down), 2023-24 then 2024-25
@real
@pytest.mark.parametrize(
    ("unit", "metric", "n", "cur", "prev", "start", "career"),
    [
        ("fga", "fg_pct", 200, 0.48, 0.43, 0.455, 0.448158),
        ("fg3a", "fg3_pct", 200, 0.405, 0.405, 0.38, 0.401948),
        ("fg3a", "fg3_pct", 50, 0.38, 0.44, 0.46, 0.402959),
    ],
)
def test_curry_windows_match_a_hand_count(rw2025, unit, metric, n, cur, prev, start, career):
    r = _row(rw2025, entity_id=CURRY, window_unit=unit, metric=metric, window_n=n)
    assert r["n"] == n and r["season"] == 2025 and r["id_source"] == "nba_stats"
    assert (r["cur"], r["prev"], r["season_start"]) == pytest.approx((cur, prev, start), abs=1e-6)
    assert r["career_baseline"] == pytest.approx(career, abs=1e-6)
    assert r["last_event_date"] == date(2025, 5, 6)


@real
def test_reading_only_this_seasons_shooters_changes_nothing(two_seasons, rw2025):
    """The stage reads history for the season's shooters only; the full league is the oracle."""
    shots = pl.concat(
        pl.read_parquet(p) for p in sorted((two_seasons / "shots" / "parquet").glob("*.parquet"))
    )
    master = pl.read_parquet(two_seasons / MASTER, columns=["game_id", "game_date_est"])
    dates = master.select(
        "game_id", game_date=pl.col("game_date_est").str.slice(0, 10).str.to_date()
    )
    full = rolling_windows(shot_events(shots, dates), 2025).with_columns(
        id_source=pl.lit("nba_stats")
    )
    assert_frame_equal(rw2025, full)
    assert rw2025["entity_id"].n_unique() > 500, "every 2024-25 shooter, not just Curry"
