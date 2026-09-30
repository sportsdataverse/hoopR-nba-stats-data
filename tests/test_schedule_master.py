"""Schedule master (D34): raw scheduleleaguev2 rows, tree-stamped in_* flags, manifest, coverage.

Offline, fixture-backed. The load-bearing invariants: every row carries the
END-year Int ``season`` its payload was read under, the column order is pinned,
and a flag is True only when the game id is in the COMMITTED
``{base}/{key}/parquet/{stem}_{season}.parquet`` -- a missing file is False,
never unset.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import nba_stats_99_schedule_master_creation as stage99
import polars as pl
import pytest
from nba_data_build.master import (
    FLAG_SOURCES,
    build_coverage,
    build_master,
    flag_columns,
    games_in_data_repo,
    season_schedule,
    stamp_from_tree,
)

GIDS = ["0012200001", "0022200001", "0042200101"]


def _game(gid: str) -> dict:
    """One trimmed real-shape ``leagueSchedule.gameDates[].games[]`` entry."""
    team = {"teamId": 1610612764, "teamName": "Wizards", "teamTricode": "WAS", "score": 87}
    return {
        "gameId": gid,
        "gameCode": "20220930/GSWWAS",
        "gameStatus": 3,
        "gameDateEst": "2022-09-30T00:00:00Z",
        "isNeutral": False,
        "broadcasters": {"nationalBroadcasters": []},
        "homeTeam": team,
        "awayTeam": {**team, "teamId": 1610612744, "teamTricode": "GSW", "score": 96},
        "pointsLeaders": [],
    }


def _payload(gids: list[str]) -> dict:
    return {
        "meta": {},
        "leagueSchedule": {
            "seasonYear": "2022",
            "leagueId": "00",
            "gameDates": [{"gameDate": "09/30/2022 00:00:00", "games": [_game(g) for g in gids]}],
        },
    }


def _pbp(base: Path, season: int, gids: list) -> None:
    key, stem = FLAG_SOURCES["in_pbp"]
    out = base / key / "parquet"
    out.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"game_id": gids}).write_parquet(out / f"{stem}_{season}.parquet")


def test_season_frame_from_raw_payload_is_end_year_stamped():
    frame = season_schedule(_payload(GIDS), 2023)
    assert frame["game_id"].to_list() == GIDS
    assert frame.schema["season"] == pl.Int64
    assert frame["season"].unique().to_list() == [2023]  # not the feed's "2022"
    assert {"home_team_id", "away_team_tricode", "season_type_id", "is_neutral"} <= set(
        frame.columns
    )
    assert frame["season_type_id"].to_list() == ["1", "2", "4"]


def test_tree_flags_present_absent_and_missing_file(tmp_path: Path):
    _pbp(tmp_path, 2023, GIDS[:2])
    stamped = stamp_from_tree(season_schedule(_payload(GIDS), 2023), tmp_path, 2023)
    assert stamped["in_pbp"].to_list() == [True, True, False]
    # No officials/boxscore/roster parquet committed for 2023: every game False.
    for flag in set(flag_columns()) - {"in_pbp"}:
        assert stamped[flag].to_list() == [False, False, False]


def test_tree_flags_restore_int_origin_ids(tmp_path: Path):
    """An Int64 committed game_id (22200001) must still match "0022200001"."""
    _pbp(tmp_path, 2023, [int(GIDS[1])])
    stamped = stamp_from_tree(season_schedule(_payload(GIDS), 2023), tmp_path, 2023)
    assert stamped["in_pbp"].to_list() == [False, True, False]


def test_stage99_builds_all_three_artifacts_from_raw(tmp_path: Path):
    raw, base = tmp_path / "raw", tmp_path / "nba_stats"
    (raw / "scheduleleaguev2").mkdir(parents=True)
    (raw / "scheduleleaguev2" / "2023.json").write_text(json.dumps(_payload(GIDS)))
    (raw / "scheduleleaguev2" / "2024.json").write_text(json.dumps(_payload(["0022300001"])))
    _pbp(base, 2023, [GIDS[1]])

    assert stage99.main(["--base", str(base), "--raw-root", str(raw)]) == 0

    master = pl.read_parquet(base / "nba_stats_schedule_master.parquet")
    assert master.columns == sorted(master.columns)  # pinned order
    assert "PBP" not in master.columns
    assert set(flag_columns()) <= set(master.columns)
    assert master.schema["season"] == pl.Int64
    assert master.select("season", "game_id").rows() == [
        (2023, GIDS[0]),
        (2023, GIDS[1]),
        (2023, GIDS[2]),
        (2024, "0022300001"),
    ]
    assert master["in_pbp"].to_list() == [False, True, False, False]  # 2024: no file
    manifest = pl.read_parquet(base / "nba_stats_games_in_data_repo.parquet")
    assert manifest["game_id"].to_list() == [GIDS[1]]
    assert (base / "nba_stats_schedule_coverage.parquet").is_file()


def test_stage99_fails_without_any_raw_season(tmp_path: Path):
    assert stage99.main(["--base", str(tmp_path), "--raw-root", str(tmp_path / "none")]) == 1


def _yearly(season: int, gids: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "game_id": gids,
            "season": [season] * len(gids),
            "season_type_id": ["2"] * (len(gids) - 1) + ["4"],
            "game_date": [dt.date(2023, 10, 24)] * len(gids),
        }
    )


def test_manifest_keeps_only_games_with_a_flag():
    frame = _yearly(2024, GIDS).with_columns(pl.Series(flag_columns()[0], [True, False, False]))
    master = build_master([frame])
    manifest = games_in_data_repo(master)
    assert manifest["game_id"].to_list() == [GIDS[0]]
    assert manifest.columns == master.columns  # same schema, filtered rows


def test_coverage_grain_and_rates():
    frame = _yearly(2024, GIDS).with_columns(pl.Series(flag_columns()[0], [True, True, False]))
    coverage = build_coverage(build_master([frame]))
    assert coverage.height == 2  # (2024, "2") + (2024, "4")
    regular = coverage.filter(pl.col("season_type_id") == "2").to_dicts()[0]
    assert regular["n_games"] == 2
    assert regular[f"pct_{flag_columns()[0]}"] == 1.0
    assert str(regular["first_date"]) == "2023-10-24"


def test_coverage_dates_are_chronological_not_lexical():
    """The feed's "MM/DD/YYYY" game_date sorts January before October."""
    frame = _yearly(2023, GIDS[1:]).with_columns(
        pl.Series("game_date", ["01/01/2023 00:00:00", "10/18/2022 00:00:00"]),
        pl.Series("game_date_est", ["2023-01-01T00:00:00Z", "2022-10-18T00:00:00Z"]),
        pl.Series("season_type_id", ["2", "2"]),
    )
    row = build_coverage(build_master([frame])).to_dicts()[0]
    assert (row["first_date"], row["last_date"]) == ("2022-10-18", "2023-01-01")


def test_build_master_requires_frames():
    with pytest.raises(ValueError, match="at least one season frame"):
        build_master([])
