"""Stage 18 ``metric_curves`` (F4-T4) on ONE real committed season, copied to a tmp tree.

The oracle is recomputed from the same ``shots`` file under the same season-type
filter, so the test fails if the adapter's population or success definition
drifts; the bucket, dtype and id assertions pin the sdv-py contract this
dataset publishes under.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import polars as pl
import pytest
from nba_data_build import docs
from nba_data_build.models import MODELS, polars_schema
from nba_data_build.reshape import build, cli, datasets
from sportsdataverse.metric_curves import BUCKET_EDGES, OUTPUT_SCHEMA

REPO = Path(__file__).resolve().parents[1]
#: 2024-25: the committed file carries play-in (5) and NBA Cup final (6) shots
#: beside the regular season (2) and playoffs (4), so the season-type filter is
#: live on this season -- dropping it changes the count.
SEASON = 2025
SHOTS = REPO / "nba_stats" / "shots" / "parquet" / f"shots_{SEASON}.parquet"
CORE = ("2", "4")

#: Reads the committed nba_stats/ tree, which PR CI does not check out.
real = pytest.mark.archive


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not SHOTS.is_file():
        pytest.skip(f"no committed shots at {SHOTS}")
    base = tmp_path_factory.mktemp("tree") / "nba_stats"
    (base / "shots" / "parquet").mkdir(parents=True)
    shutil.copy(SHOTS, base / "shots" / "parquet" / SHOTS.name)
    return base


@pytest.fixture(scope="module")
def shots() -> pl.DataFrame:
    if not SHOTS.is_file():
        pytest.skip(f"no committed shots at {SHOTS}")
    return pl.read_parquet(SHOTS)


@pytest.fixture(scope="module")
def curves(base: Path) -> pl.DataFrame:
    return build.build_metric_curves(build.committed_shots(base, SEASON))


def _league(curves: pl.DataFrame) -> pl.DataFrame:
    return curves.filter(pl.col("entity_type") == "league")


@real
def test_league_curve_sums_to_the_core_season_shots(curves, shots):
    core = shots.filter(
        pl.col("season_type_id").is_in(CORE)
        & pl.col("shot_distance").is_not_null()
        & pl.col("shot_result").is_in(["Made", "Missed"])
    )
    assert core.height < shots.height, "the filter must be live on this season"
    league = _league(curves)
    assert league["attempts"].sum() == core.height
    assert league["successes"].sum() == core.filter(pl.col("shot_result") == "Made").height
    assert set(league["metric"]) == {"fg_pct_by_shot_distance"}
    assert set(curves["season"]) == {SEASON}
    assert (curves["attempts"] > 0).all(), "an empty bucket is absent, never a zero row"
    assert (curves["rate"] == curves["successes"] / curves["attempts"]).all()
    # team and player curves partition the same attempts
    for kind in ("team", "player"):
        assert curves.filter(pl.col("entity_type") == kind)["attempts"].sum() == core.height


@real
def test_bins_are_one_foot_to_35_then_35_50_and_50_95(curves):
    edges = BUCKET_EDGES["fg_pct_by_shot_distance"]
    pairs = set(zip(curves["x_lo"], curves["x_hi"]))
    assert pairs <= set(zip(edges[:-1], edges[1:]))
    assert all(hi - lo == 1 for lo, hi in pairs if lo < 35)
    league = set(zip(_league(curves)["x_lo"], _league(curves)["x_hi"]))
    assert {(35.0, 50.0), (50.0, 95.0)} <= league, "35-50 and 50-95 are one bucket each"
    assert max(hi for _, hi in pairs) == 95.0


@real
def test_contract_dtypes_ids_and_entities(curves):
    assert dict(curves.schema) == OUTPUT_SCHEMA
    assert set(curves["id_source"]) == {"nba_stats"}, "stamped by the adapter, not the stage"
    assert set(curves["entity_type"]) == {"league", "team", "player"}
    league = _league(curves)
    rest = curves.filter(pl.col("entity_type") != "league")
    assert league["entity_id"].null_count() == league.height
    assert rest["entity_id"].null_count() == 0
    assert rest["entity_id"].str.contains(r"^\d+$").all(), "ids are integer strings, never 123.0"
    player = curves.filter(pl.col("entity_type") == "player")
    assert player["team_id"].null_count() == 0
    assert player["team_id"].str.contains(r"^\d+$").all()
    assert curves["down"].null_count() == curves.height
    assert curves["epa_per_att"].null_count() == curves.height
    # one row per (entity, bucket)
    assert curves.height == curves.select("entity_type", "entity_id", "x_lo").n_unique()


@real
def test_missing_season_returns_the_contract_schema(base):
    empty = build.build_metric_curves(build.committed_shots(base, 1996))
    assert empty.height == 0 and dict(empty.schema) == OUTPUT_SCHEMA


@real
def test_cli_reuses_this_runs_shots_and_falls_back_to_the_tree(monkeypatch, base):
    """The daily run builds shots first and must not read yesterday's committed file."""
    ds = datasets.BY_KEY["metric_curves"]
    reads: list[tuple[object, int]] = []

    def fake_committed(b, s):
        reads.append((b, s))
        return pl.DataFrame()

    monkeypatch.setattr(cli._build, "committed_shots", fake_committed)
    in_memory = pl.read_parquet(base / "shots" / "parquet" / SHOTS.name).head(200)
    out = cli.build_dataset("root", ds, SEASON, _shots=in_memory, base=base)
    assert reads == [] and out.height > 0
    out = cli.build_dataset("root", ds, SEASON, base=base)
    assert reads == [(base, SEASON)] and out.height == 0


def test_stage_18_is_registered_everywhere():
    ds = datasets.BY_KEY["metric_curves"]
    assert (ds.stem, ds.release_tag, ds.level, ds.endpoint) == (
        "metric_curves",
        "nba_stats_metric_curves",
        "derived",
        None,
    )
    assert datasets.DATASETS[-1].key == "metric_curves", "stage numbers follow registry order"
    notes = datasets.RELEASE_NOTES["nba_stats_metric_curves"]
    for phrase in ("shot distance", "1997", "season_type_id", "id_source"):
        assert phrase in notes
    assert docs.BUILDER["metric_curves"] == "python/nba_stats_18_metric_curves_creation.py"
    assert "metric_curves" in MODELS
    assert polars_schema("metric_curves") == pl.Schema(OUTPUT_SCHEMA)
