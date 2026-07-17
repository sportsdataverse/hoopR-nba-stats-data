"""Tests for CLI season resolution and publish dispatch."""
import argparse

import nba_data_build.cli as C


def test_resolve_seasons_latest_n_window_is_inclusive_of_through(monkeypatch):
    # semantics-lock, not the regression guard (see test_build.py) -- the actual
    # off-by-one this migration fixed lived entirely in build.py's build_season()
    # (a stray `season + 1`) and never touched _resolve_seasons, whose arithmetic
    # was unchanged by that fix. This instead locks a distinct, narrower contract
    # that belongs to _resolve_seasons itself: --through defaults to
    # most_recent_nba_season() with NO adjustment, and --latest-n selects the
    # inclusive end-year window [through - latest_n + 1, through] -- asserting the
    # full window (not just its last element) so a start- or count-boundary
    # off-by-one in this function's own range math would fail the test.
    monkeypatch.setattr(C, "most_recent_nba_season", lambda: 2026)
    seasons = C._resolve_seasons(
        argparse.Namespace(seasons=None, through=None, latest_n=3, first=None)
    )
    assert seasons == [2024, 2025, 2026]


def test_explicit_seasons_bypass_detection(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(C, "build", lambda seasons, out_dir, cache_dir=None: seen.update(seasons=seasons) or [])
    monkeypatch.setattr(C, "detect_missing_seasons", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not detect")))
    rc = C.main(["--seasons", "2022", "2023", "--out", str(tmp_path)])
    assert rc == 0 and seen["seasons"] == [2022, 2023]


def test_incremental_detects_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "most_recent_nba_season", lambda: 2024)
    monkeypatch.setattr(C, "published_seasons", lambda tag, repo: {2021, 2022})
    seen = {}
    monkeypatch.setattr(C, "build", lambda seasons, out_dir, cache_dir=None: seen.update(seasons=seasons) or [])
    rc = C.main(["--out", str(tmp_path)])
    assert rc == 0 and seen["seasons"] == [2023, 2024]


def test_publish_flag_calls_uploader(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "build", lambda seasons, out_dir, cache_dir=None: [])
    tags = []
    monkeypatch.setattr(C, "upload_artifacts", lambda d, tag, repo, **k: tags.append(tag) or {"uploaded": 0})
    C.main(["--seasons", "2023", "--out", str(tmp_path), "--publish"])
    assert "nba_stats_rapm" in tags and "nba_stats_possessions" in tags
