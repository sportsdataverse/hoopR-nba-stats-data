"""Tests for CLI season resolution and publish dispatch."""
import nba_data_build.cli as C


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
