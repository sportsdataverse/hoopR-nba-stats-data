"""Stage 19 ``injury_report`` on vendored real rows (``tests/fixtures/injury_report``).

Two report versions of 2026-01-08 and one Summer League version of 2026-07-15 from
the raw store, with the 2025-26 schedule master, player boxscores and rosters for
those teams (``make_fixture.py`` regenerates them). Every person-id path has a real
case: an exact name on the team, a league-wide name, a season-long absence found
only on the roster, and a player matched nowhere.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl
import pytest
from nba_data_build import docs
from nba_data_build.models import MODELS, check_frame, polars_schema
from nba_data_build.reshape import cli, datasets
from nba_data_build.reshape.injury_report import SCHEMA, build_injury_report

FX = Path(__file__).parent / "fixtures" / "injury_report"
RAW, BASE = FX / "raw", FX / "nba_stats"
SEASON, TODAY = 2026, dt.date(2026, 10, 30)


@pytest.fixture(scope="module")
def report() -> pl.DataFrame:
    return build_injury_report(RAW, SEASON, BASE, today=TODAY)


def _player(report: pl.DataFrame, name: str) -> dict:
    return report.filter(pl.col("report_player_name") == name).row(0, named=True)


def test_schema_matches_the_declared_model(report) -> None:
    assert dict(report.schema) == SCHEMA
    assert polars_schema("injury_report") == pl.Schema(SCHEMA)
    assert check_frame("injury_report", report) == []


@pytest.mark.parametrize(
    ("name", "person_id", "method"),
    [
        ("Kessler, Walker", 1631117, "exact"),  # on the Jazz's boxscores
        ("Haliburton, Tyrese", 1630169, "roster"),  # out all season: no boxscore row
        ("Irving, Kyrie", 202681, "roster"),
        ("Exum, Dante", None, None),  # on neither the boxscores nor the roster
    ],
)
def test_person_ids_follow_the_match_order(report, name, person_id, method) -> None:
    row = _player(report, name)
    assert (row["person_id"], row["match_method"]) == (person_id, method)


def test_a_postponed_game_keeps_its_team_but_no_game_id(report) -> None:
    """MIA@CHI was printed for 01-08 and played 01-29 (0022500529, in the fixture)."""
    rows = report.filter(pl.col("report_matchup") == "MIA@CHI")
    assert rows.height > 0 and rows["game_id"].is_null().all()
    assert set(rows["team_id"].to_list()) <= {1610612748, 1610612741}  # MIA, CHI
    assert rows["team_id"].is_not_null().all()


def test_game_ids_join_on_date_and_tricodes(report) -> None:
    row = _player(report, "Haliburton, Tyrese")
    assert (row["game_id"], row["team_id"], row["report_matchup"]) == (
        "0022500528",
        1610612754,
        "IND@CHA",
    )


def test_an_unsubmitted_team_is_kept_as_one_row(report) -> None:
    nys = report.filter(pl.col("reason") == "NOT YET SUBMITTED")
    assert nys.height > 0
    assert nys["report_player_name"].is_null().all() and nys["current_status"].is_null().all()
    # January only: the trimmed fixture schedule has no Spurs game for July's UTA@SAS row
    jan = nys.filter(pl.col("report_datetime").dt.month() == 1)
    assert jan.height > 0 and jan["team_id"].is_not_null().all()


def test_the_season_year_runs_through_july_and_stops_at_today(report) -> None:
    days = set(report["report_datetime"].dt.date().to_list())
    assert days == {dt.date(2026, 1, 8), dt.date(2026, 7, 15)}  # Summer League files in July
    early = build_injury_report(RAW, SEASON, BASE, today=dt.date(2026, 3, 1))
    assert set(early["report_datetime"].dt.date().to_list()) == {dt.date(2026, 1, 8)}


def test_a_season_missing_from_the_schedule_is_empty() -> None:
    out = build_injury_report(RAW, 2019, BASE, today=TODAY)
    assert out.height == 0 and dict(out.schema) == SCHEMA


def test_this_runs_boxscores_take_precedence_over_the_committed_file(report) -> None:
    """The daily run builds player_boxscores first; a current season has no committed file."""
    box = pl.read_parquet(BASE / "player_boxscores" / "parquet" / "player_boxscores_2026.parquet")
    without_kessler = build_injury_report(
        RAW, SEASON, BASE, box=box.filter(pl.col("person_id") != 1631117), today=TODAY
    )
    assert _player(report, "Kessler, Walker")["match_method"] == "exact"
    assert _player(without_kessler, "Kessler, Walker")["match_method"] != "exact"


def test_the_cli_passes_this_runs_boxscores(monkeypatch) -> None:
    seen = {}

    def fake(root, season, base, box):
        seen["box"] = box
        return pl.DataFrame(schema=SCHEMA)

    monkeypatch.setattr(cli, "build_injury_report", fake)
    marker = pl.DataFrame({"person_id": [1]})
    cli.build_dataset("root", datasets.BY_KEY["injury_report"], SEASON, _box=marker, base=BASE)
    assert seen["box"] is marker


def test_stage_19_is_registered_everywhere() -> None:
    ds = datasets.BY_KEY["injury_report"]
    assert (ds.stem, ds.release_tag, ds.level, ds.endpoint, ds.season_floor) == (
        "injury_report",
        "nba_stats_injury_report",
        "derived",
        None,
        2019,
    )
    assert datasets.DATASETS[-1] is ds, "stage numbers follow registry order"
    notes = datasets.RELEASE_NOTES["nba_stats_injury_report"]
    for phrase in ("report_datetime", "NOT YET SUBMITTED", "match_method", "2018-12-17"):
        assert phrase in notes
    assert docs.BUILDER["injury_report"] == "python/nba_stats_19_injury_report_creation.py"
    assert (Path(__file__).parents[1] / docs.BUILDER["injury_report"]).is_file()
    assert "injury_report" in MODELS


def test_an_ambiguous_name_on_the_team_is_not_an_exact_match(report) -> None:
    """A second (relabeled real) Walker Kessler on the Jazz must not be guessed between."""
    box = pl.read_parquet(BASE / "player_boxscores" / "parquet" / "player_boxscores_2026.parquet")
    twin = box.filter(pl.col("person_id") == 1631117).with_columns(
        pl.lit(999, dtype=pl.Int64).alias("person_id")
    )
    out = build_injury_report(RAW, SEASON, BASE, box=pl.concat([box, twin]), today=TODAY)
    row = _player(out, "Kessler, Walker")
    assert row["match_method"] != "exact" and row["person_id"] != 999
