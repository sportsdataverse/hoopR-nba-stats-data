import subprocess

import pytest

from nba_data_build.publish import plan_uploads, published_seasons, upload_artifacts


def _mk(tmp_path):
    d = tmp_path / "rapm"
    d.mkdir()
    (d / "nba_rapm_2023.parquet").write_bytes(b"x")
    (d / "nba_rapm_2024.parquet").write_bytes(b"y")
    return d


def test_plan_uploads_finds_parquet(tmp_path):
    d = _mk(tmp_path)
    assert sorted(p.name for p in plan_uploads(d)) == ["nba_rapm_2023.parquet", "nba_rapm_2024.parquet"]


def test_upload_creates_release_when_missing_then_uploads(tmp_path):
    d = _mk(tmp_path)
    calls = []
    res = upload_artifacts(
        d,
        tag="nba_stats_rapm",
        repo="sportsdataverse/sportsdataverse-data",
        runner=lambda args: calls.append(args),
        exists_check=lambda t, r: False,
    )
    # one 'release create' then one 'release upload --clobber' per file
    assert calls[0][:2] == ["release", "create"] and "nba_stats_rapm" in calls[0]
    uploads = [c for c in calls if c[:2] == ["release", "upload"]]
    assert len(uploads) == 2 and all("--clobber" in c for c in uploads)
    assert res["uploaded"] == 2


def test_upload_skips_create_when_release_exists(tmp_path):
    d = _mk(tmp_path)
    calls = []
    upload_artifacts(
        d, tag="nba_stats_rapm", repo="r/r", runner=lambda args: calls.append(args), exists_check=lambda t, r: True
    )
    assert not any(c[:2] == ["release", "create"] for c in calls)


def test_dry_run_uploads_nothing(tmp_path):
    d = _mk(tmp_path)
    calls = []
    res = upload_artifacts(
        d, tag="t", repo="r/r", dry_run=True, runner=lambda args: calls.append(args), exists_check=lambda t, r: True
    )
    assert calls == [] and res["uploaded"] == 0


def test_published_seasons_parses_asset_names():
    fake = "nba_rapm_2021.parquet\nnba_rapm_2023.parquet\nother.txt\n"
    assert published_seasons("nba_stats_rapm", "r/r", runner=lambda args: fake) == {2021, 2023}


def test_published_seasons_returns_empty_when_release_absent():
    """A CalledProcessError whose stderr says 'release not found' -> empty set (first-run scenario)."""

    def runner_missing(args: list[str]) -> str:
        raise subprocess.CalledProcessError(1, "gh", stderr="release not found")

    assert published_seasons("nba_stats_rapm", "r/r", runner=runner_missing) == set()


def test_published_seasons_reraises_on_auth_failure():
    """A CalledProcessError for auth / permission errors must propagate, not silently return empty."""

    def runner_auth_fail(args: list[str]) -> str:
        raise subprocess.CalledProcessError(1, "gh", stderr="HTTP 401: Bad credentials")

    with pytest.raises(subprocess.CalledProcessError):
        published_seasons("nba_stats_rapm", "r/r", runner=runner_auth_fail)
