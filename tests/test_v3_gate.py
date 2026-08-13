"""Offline unit tests for the section-9.3 gate diff logic."""

from __future__ import annotations

import polars as pl
from nba_data_build import v3_gate as vg


def _sched(rows: list[tuple[str, int, int]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "game_id": [r[0] for r in rows],
            "home_pts": [r[1] for r in rows],
            "away_pts": [r[2] for r in rows],
        }
    )


def _legacy_sched(rows: list[tuple[str, int, int]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "game_id": [r[0] for r in rows],
            "home_team_score": [r[1] for r in rows],
            "away_team_score": [r[2] for r in rows],
        }
    )


def test_core_ids_excludes_noncore_types() -> None:
    ids = {"0020500001", "0040500001", "0010500001", "0030500001", "0050500001"}
    assert vg.core_ids(ids) == {"0020500001", "0040500001"}


def test_legacy_span_naming() -> None:
    assert vg.legacy_span(2006) == "2005-06"
    assert vg.legacy_span(2000) == "1999-00"


def test_gate_schedule_ok_with_explained_preseason() -> None:
    staged = _sched([("0020500001", 101, 99)])
    legacy = _legacy_sched([("0020500001", 101, 99), ("0010500001", 90, 80)])
    f = vg.gate_schedule(2006, staged, legacy, raw_game_count=None)
    assert f["verdict"] == "OK"
    assert "legacy_excluded_noncore=1" in f["detail"]


def test_gate_schedule_flags_missing_and_score_mismatch() -> None:
    staged = _sched([("0020500001", 101, 99)])
    legacy = _legacy_sched([("0020500001", 100, 99), ("0020500002", 90, 80)])
    f = vg.gate_schedule(2006, staged, legacy, raw_game_count=None)
    assert f["verdict"] == "DIFF"
    assert "missing_in_v3=1" in f["detail"]
    assert "score_mismatch=1" in f["detail"]


def test_gate_schedule_noncore_score_disagreement_is_not_a_diff() -> None:
    """v3 non-core scores come from a different source than legacy's -- never a DIFF."""
    staged = _sched([("0020500001", 101, 99), ("0010500001", 0, 0)])
    legacy = _legacy_sched([("0020500001", 101, 99), ("0010500001", 90, 80)])
    f = vg.gate_schedule(2006, staged, legacy, raw_game_count=None)
    assert f["verdict"] == "OK"
    assert "scores_compared=1" in f["detail"] and "score_mismatch=0" in f["detail"]


def test_gate_schedule_null_scores_are_not_mismatches() -> None:
    staged = _sched([("0020500001", 101, 99)])
    legacy = _legacy_sched([("0020500001", None, None)])  # type: ignore[list-item]
    f = vg.gate_schedule(2006, staged, legacy, raw_game_count=None)
    assert f["verdict"] == "OK"
    assert "scores_compared=0" in f["detail"]


def _pbp(games: dict[str, tuple[int, int, int]]) -> pl.DataFrame:
    rows = []
    for gid, (n_events, home, away) in games.items():
        for i in range(n_events):
            last = i == n_events - 1
            rows.append(
                {
                    "game_id": gid,
                    "score_home": home if last else 0,
                    "score_away": away if last else 0,
                }
            )
    return pl.DataFrame(rows)


def test_gate_pbp_legacy_ok() -> None:
    staged = _pbp({"0020500001": (10, 101, 99)})
    sched = _sched([("0020500001", 101, 99)])
    legacy = pl.DataFrame({"game_id": ["0020500001"]})
    f = vg.gate_pbp(2006, staged, sched, legacy, raw_ids=None)
    assert f["verdict"] == "OK"


def test_gate_pbp_score_vs_schedule_mismatch_is_diff() -> None:
    staged = _pbp({"0020500001": (10, 100, 99)})
    sched = _sched([("0020500001", 101, 99)])
    legacy = pl.DataFrame({"game_id": ["0020500001"]})
    f = vg.gate_pbp(2006, staged, sched, legacy, raw_ids=None)
    assert f["verdict"] == "DIFF"
    assert "score_mismatch=1" in f["detail"]


def test_gate_pbp_no_legacy_validates_against_raw_store() -> None:
    staged = _pbp({"0022300001": (10, 110, 105)})
    sched = _sched([("0022300001", 110, 105)])
    ok = vg.gate_pbp(2024, staged, sched, None, raw_ids={"0022300001"})
    assert ok["verdict"] == "NO_LEGACY_OK"
    short = vg.gate_pbp(2024, staged, sched, None, raw_ids={"0022300001", "0022300002"})
    assert short["verdict"] == "DIFF"
    assert "uncompiled=1" in short["detail"]


def test_gate_missing_staged_is_fatal() -> None:
    assert vg.gate_schedule(2006, None, None, None)["verdict"] == "MISSING_STAGED"
    assert vg.gate_pbp(2006, None, None, None, None)["verdict"] == "MISSING_STAGED"


def test_run_gate_exit_code(tmp_path) -> None:
    # Nothing staged for the requested season -> MISSING_STAGED -> exit 1.
    findings, code = vg.run_gate([2006], tmp_path, tmp_path, tmp_path)
    assert code == 1
    assert {f["verdict"] for f in findings} == {"MISSING_STAGED", "MISSING_SUMMARY"}


def _summary(**over) -> dict:
    base = {
        "season": 2006,
        "status": "built",
        "games_failed": 0,
        "games_indexed": 1300,
        "games_uncaptured": 0,
        "games_no_pbp": 113,
        "games_processed": 1187,
        "failed_sample": [],
    }
    base.update(over)
    return base


def test_gate_build_fails_a_season_with_failed_games() -> None:
    """The D26c blind spot: games_uncaptured=0 must not carry a season on its own."""
    ok = vg.gate_build(2006, _summary())
    assert ok["verdict"] == "OK"
    assert "games_no_pbp=113" in ok["detail"]

    bad = vg.gate_build(2006, _summary(games_failed=113, failed_sample=["0019600001"]))
    assert bad["verdict"] == "DIFF"
    assert "games_failed=113" in bad["detail"] and "0019600001" in bad["detail"]


def test_gate_build_missing_summary_is_unverified_not_ok() -> None:
    finding = vg.gate_build(2006, None)
    assert finding["verdict"] == "MISSING_SUMMARY"


def test_run_gate_surfaces_failed_games(tmp_path) -> None:
    import json

    from nba_data_build import v3_backfill as vb

    for p in vb.season_paths(tmp_path, 2006).values():
        _sched([("0020500001", 101, 99)]).write_parquet(p)
    vb.summary_path(tmp_path, 2006).write_text(
        json.dumps(_summary(games_failed=7)), encoding="utf-8"
    )
    findings, code = vg.run_gate([2006], tmp_path, tmp_path, tmp_path)
    build = next(f for f in findings if f["family"] == "build")
    assert build["verdict"] == "DIFF" and code == 1
