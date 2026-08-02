"""Tests for the ``pipeline`` CLI verb: dry-run e2e, publish-gating, and _publish itself.

All fully offline -- discovery, the scrape client's transport, and _publish's git/gh
runners are injected so no network or real git/gh command ever runs from this suite.
"""

import json
import shutil

import polars as pl
import pytest
from nba_data_build import pipeline_cli
from nba_data_build.scrape.client import V3Client


def _fake_transport(tmp_path):
    kind_dir = {"pbp": "pbpv3", "box": "boxv3"}

    def transport(kind, gid, **params):
        d = kind_dir.get(kind, "boxv3_periods")
        return json.loads(
            (tmp_path / "nba_stats" / "json" / d / f"{gid}.json").read_text()
        )

    return transport


def test_dry_run_builds_but_does_not_publish(tmp_path, monkeypatch):
    shutil.copytree("tests/fixtures/raw/nba_stats", tmp_path / "nba_stats")
    # discovery + client are injected so no network is touched
    monkeypatch.setattr(
        pipeline_cli,
        "_discover_finished",
        lambda season, root: [
            {
                "game_id": "0022300001",
                "game_status": 3,
                "home_team_id": 1610612744,
                "n_periods": 4,
            }
        ],
    )
    monkeypatch.setattr(
        pipeline_cli,
        "_make_client",
        lambda: V3Client(transport=_fake_transport(tmp_path)),
    )
    published = {"called": False}
    monkeypatch.setattr(
        pipeline_cli, "_publish", lambda *a, **k: published.__setitem__("called", True)
    )
    rc = pipeline_cli.main(["--seasons", "2023", "--root", str(tmp_path), "--dry-run"])
    assert rc == 0
    assert (
        tmp_path
        / "nba_stats"
        / "possessions"
        / "parquet"
        / "nba_possessions_v3_2023.parquet"
    ).exists()
    assert published["called"] is False  # dry-run must NOT publish


def test_publish_requires_explicit_flag(tmp_path, monkeypatch):
    # no --publish and no --dry-run: guard still runs, nothing outward happens
    monkeypatch.setattr(pipeline_cli, "_discover_finished", lambda s, r: [])
    rc = pipeline_cli.main(["--seasons", "2023", "--root", str(tmp_path)])
    assert rc == 0


def test_publish_flag_alone_calls_publish(tmp_path, monkeypatch):
    """--publish (no --dry-run) IS the one combination that reaches _publish."""
    monkeypatch.setattr(pipeline_cli, "_discover_finished", lambda s, r: [])
    called = {}
    monkeypatch.setattr(
        pipeline_cli,
        "_publish",
        lambda root, seasons, **k: called.update(root=root, seasons=seasons, kwargs=k),
    )
    rc = pipeline_cli.main(["--seasons", "2023", "--root", str(tmp_path), "--publish"])
    assert rc == 0
    assert called["seasons"] == [2023]


def test_dry_run_wins_when_both_flags_set(tmp_path, monkeypatch):
    """--dry-run alongside --publish must still suppress the publish call."""
    monkeypatch.setattr(pipeline_cli, "_discover_finished", lambda s, r: [])
    published = {"called": False}
    monkeypatch.setattr(
        pipeline_cli, "_publish", lambda *a, **k: published.__setitem__("called", True)
    )
    rc = pipeline_cli.main(
        ["--seasons", "2023", "--root", str(tmp_path), "--publish", "--dry-run"]
    )
    assert rc == 0
    assert published["called"] is False


def test_dry_run_writes_schedule_snapshot_and_flips_availability_true(
    tmp_path, monkeypatch
):
    """End-to-end: after a real rollup, the season snapshot + master both show POSS/LINEUP True."""
    shutil.copytree("tests/fixtures/raw/nba_stats", tmp_path / "nba_stats")
    monkeypatch.setattr(
        pipeline_cli,
        "_discover_finished",
        lambda season, root: [
            {
                "game_id": "0022300001",
                "game_status": 3,
                "home_team_id": 1610612744,
                "n_periods": 4,
            }
        ],
    )
    monkeypatch.setattr(
        pipeline_cli,
        "_make_client",
        lambda: V3Client(transport=_fake_transport(tmp_path)),
    )
    monkeypatch.setattr(
        pipeline_cli, "_publish", lambda *a, **k: pytest.fail("must not be called")
    )

    rc = pipeline_cli.main(["--seasons", "2023", "--root", str(tmp_path), "--dry-run"])
    assert rc == 0

    snapshot = pl.read_parquet(
        tmp_path
        / "nba_stats"
        / "schedule_v3"
        / "parquet"
        / "nba_schedule_v3_2023.parquet"
    )
    row = snapshot.filter(pl.col("game_id") == "0022300001").to_dicts()[0]
    assert row["POSS"] is True and row["LINEUP"] is True and row["PBP_V3"] is True

    master = pl.read_parquet(
        tmp_path / "nba_stats" / "nba_stats_schedule_master.parquet"
    )
    mrow = master.filter(pl.col("game_id") == "0022300001").to_dicts()[0]
    assert mrow["POSS"] is True and mrow["LINEUP"] is True


def test_master_upsert_preserves_other_seasons(tmp_path):
    """_upsert_master_flags must not null out a prior season's already-computed flags."""
    prior = pl.DataFrame(
        {
            "game_id": ["0022200001"],
            "season": ["2022-23"],
            "PBP_V3": [True],
            "BOX_V3": [True],
            "BOX_PERIODS": [True],
            "POSS": [True],
            "LINEUP": [True],
        }
    )
    new_season = pl.DataFrame(
        {
            "game_id": ["0022300001"],
            "PBP_V3": [True],
            "BOX_V3": [False],
            "BOX_PERIODS": [False],
            "POSS": [False],
            "LINEUP": [False],
        }
    )
    merged = pipeline_cli._upsert_master_flags(prior, new_season)
    old_row = merged.filter(pl.col("game_id") == "0022200001").to_dicts()[0]
    assert (
        old_row["POSS"] is True and old_row["LINEUP"] is True
    )  # untouched by this run
    new_row = merged.filter(pl.col("game_id") == "0022300001").to_dicts()[0]
    assert new_row["POSS"] is False and new_row["PBP_V3"] is True


def test_master_upsert_first_run_no_prior_flag_columns(tmp_path):
    """Real-world master predates the v3 flag feature -- none of the 5 flag columns
    exist yet, so the join produces zero collisions and every flag column arrives
    from new_slice unsuffixed (not f"{c}_v3new"). Regression for the exact crash hit
    on the live 2025-26 dry-run: ColumnNotFoundError on "PBP_V3_v3new"."""
    prior = pl.DataFrame({"game_id": ["0022200001"], "season": ["2022-23"], "PBP": [True]})
    new_season = pl.DataFrame(
        {
            "game_id": ["0022300001"],
            "PBP_V3": [True],
            "BOX_V3": [False],
            "BOX_PERIODS": [False],
            "POSS": [False],
            "LINEUP": [False],
        }
    )
    merged = pipeline_cli._upsert_master_flags(prior, new_season)
    old_row = merged.filter(pl.col("game_id") == "0022200001").to_dicts()[0]
    assert old_row["PBP"] is True
    assert old_row["PBP_V3"] is None  # never computed for this row
    new_row = merged.filter(pl.col("game_id") == "0022300001").to_dicts()[0]
    assert new_row["PBP_V3"] is True and new_row["POSS"] is False


def test_publish_stages_explicit_path_and_commits_preserved_subject(tmp_path):
    """_publish never uses a blind `git add -A`; subject matches the R producer's convention."""
    calls = []
    result = pipeline_cli._publish(
        tmp_path,
        [2022, 2024],
        git_runner=lambda args: calls.append(args) or "M nba_stats/foo.parquet",
    )
    assert calls[0] == ["status", "--porcelain", "--", "nba_stats"]
    assert calls[1] == ["add", "nba_stats"]
    assert calls[2][:2] == ["commit", "-m"]
    assert calls[2][2] == "NBA Stats Update (Start: 2022 End: 2024)"
    assert result == {
        "committed": True,
        "subject": "NBA Stats Update (Start: 2022 End: 2024)",
        "target": "commit",
    }


def test_publish_noop_when_nothing_staged(tmp_path):
    """An empty `git status --porcelain` means nothing to commit -- _publish must not add/commit."""
    calls = []
    result = pipeline_cli._publish(
        tmp_path, [2023], git_runner=lambda args: calls.append(args) or ""
    )
    assert calls == [
        ["status", "--porcelain", "--", "nba_stats"]
    ]  # never reached add/commit
    assert result["committed"] is False


def test_publish_target_release_mirrors_rollups(tmp_path):
    """target="release" (OD2 Option B) additionally uploads each existing per-season dataset dir."""
    for name in ("pbpv3", "possessions", "lineups"):
        d = tmp_path / "nba_stats" / name / "parquet"
        d.mkdir(parents=True)
        (d / f"x_{name}_2023.parquet").write_bytes(b"x")

    git_calls = []
    gh_calls = []
    result = pipeline_cli._publish(
        tmp_path,
        [2023],
        target="release",
        git_runner=lambda args: git_calls.append(args) or "M nba_stats/x",
        runner=lambda args: gh_calls.append(args) or "",
        exists_check=lambda tag, repo: False,  # hermetic: never probe the real remote
    )
    assert result["committed"] is True
    assert set(result["release_mirror"]) == {
        "nba_stats_pbpv3",
        "nba_stats_possessions_v3",
        "nba_stats_lineups_v3",
    }
    assert any(c[:2] == ["release", "create"] for c in gh_calls)


def test_help_lists_expected_flags():
    parser = pipeline_cli.build_pipeline_parser()
    help_text = parser.format_help()
    for flag in (
        "--seasons",
        "--root",
        "--rescrape",
        "--dry-run",
        "--publish",
        "--target",
        "--cache-dir",
    ):
        assert flag in help_text
