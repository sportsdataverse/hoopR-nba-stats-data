"""Offline tests for the D26d cutover publisher. No network, no gh, no uploads."""

from __future__ import annotations

import json
import subprocess

import polars as pl
import pytest
from nba_data_build import v3_cutover as vc
from nba_data_build import v3_gate

# --------------------------------------------------------------------------- helpers


def _stage(staging, season, families=vc.TARGETS, rows=3):
    """Write a tiny staged parquet per family; return {family: path}."""
    staging.mkdir(parents=True, exist_ok=True)
    out = {}
    for fam in families:
        p = staging / f"nba_{fam}_{season}.parquet"
        pl.DataFrame({"game_id": [f"00{i}" for i in range(rows)]}).write_parquet(p)
        out[fam] = p
    return out


class FakeGh:
    """Stand-in for `gh`. Holds an in-memory release table; records every call."""

    def __init__(self, releases=None):
        self.releases = releases or {}
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["release", "view"]:
            tag = args[2]
            if tag not in self.releases:
                raise subprocess.CalledProcessError(1, "gh")
            return json.dumps({"assets": self.releases[tag]})
        if args[:2] == ["release", "upload"]:
            tag, path = args[2], args[3]
            from pathlib import Path

            name = Path(path).name
            assets = self.releases.setdefault(tag, [])
            assets[:] = [a for a in assets if a["name"] != name]
            assets.append(
                {
                    "name": name,
                    "size": Path(path).stat().st_size,
                    "updatedAt": "2026-08-11T00:00:00Z",
                }
            )
            return ""
        if args[:2] == ["release", "delete"]:
            self.releases.pop(args[2], None)
            return ""
        return ""

    def uploads(self):
        return [a[3] for a in self.calls if a[:2] == ["release", "upload"]]


def _asset(name, size, updated="2023-03-30T17:42:36Z"):
    return {"name": name, "size": size, "updatedAt": updated}


# --------------------------------------------------------------------------- classify


def test_classify_new_when_no_remote():
    assert vc.classify(10, "abc", None, None) == "NEW"


def test_classify_replace_when_remote_exists_without_receipt():
    assert vc.classify(10, "abc", {"size": 10}, None) == "REPLACE"


def test_classify_unchanged_needs_matching_receipt_and_size():
    remote = {"size": 10}
    assert vc.classify(10, "abc", remote, {"sha256": "abc", "size": 10}) == "UNCHANGED"


def test_classify_size_match_alone_is_not_identity():
    """Two different parquets can share a byte count -- never call that UNCHANGED."""
    assert vc.classify(10, "abc", {"size": 10}, {"sha256": "OTHER", "size": 10}) == "REPLACE"


def test_classify_replace_when_receipt_matches_but_remote_size_drifted():
    assert vc.classify(10, "abc", {"size": 99}, {"sha256": "abc", "size": 10}) == "REPLACE"


# --------------------------------------------------------------------------- manifest


def test_stage_rows_reports_bytes_and_rows(tmp_path):
    _stage(tmp_path, 2006, rows=7)
    rows = vc.stage_rows(tmp_path, [2006], vc.TARGETS)
    assert {r["family"] for r in rows} == set(vc.TARGETS)
    assert all(r["rows"] == 7 and r["size"] > 0 and len(r["sha256"]) == 64 for r in rows)


def test_stage_rows_skips_missing_seasons(tmp_path):
    _stage(tmp_path, 2006)
    assert vc.stage_rows(tmp_path, [2006, 2007], vc.TARGETS) == vc.stage_rows(
        tmp_path, [2006], vc.TARGETS
    )


def test_build_manifest_classifies_against_live_tag(tmp_path):
    _stage(tmp_path, 2006)
    staged = vc.stage_rows(tmp_path, [2006], vc.TARGETS)
    pbp = next(r for r in staged if r["family"] == "play_by_play")
    remote = {
        "nba_stats_pbp": {
            "nba_play_by_play_2006.parquet": {"size": 1, "updatedAt": "2023-03-30T17:42:36Z"}
        }
    }

    manifest = vc.build_manifest(staged, remote, {})
    by_family = {r["family"]: r for r in manifest}
    assert by_family["play_by_play"]["verdict"] == "REPLACE"
    assert by_family["play_by_play"]["remote_size"] == 1
    assert by_family["play_by_play"]["remote_updated_at"] == "2023-03-30T17:42:36Z"
    assert by_family["schedule"]["verdict"] == "NEW"
    assert by_family["schedule"]["remote_size"] is None
    assert pbp["asset"] == "nba_play_by_play_2006.parquet"


def test_build_manifest_unchanged_from_receipt(tmp_path):
    _stage(tmp_path, 2006)
    staged = vc.stage_rows(tmp_path, [2006], vc.TARGETS)
    row = next(r for r in staged if r["family"] == "possessions")
    remote = {row["tag"]: {row["asset"]: {"size": row["size"], "updatedAt": "x"}}}
    receipts = {f"{row['tag']}/{row['asset']}": {"sha256": row["sha256"], "size": row["size"]}}

    manifest = vc.build_manifest(staged, remote, receipts)
    assert next(r for r in manifest if r["family"] == "possessions")["verdict"] == "UNCHANGED"


def test_shadowed_assets_surfaces_untouched_legacy_names(tmp_path):
    """The legacy START-year assets the loaders still read must show up."""
    _stage(tmp_path, 2006)
    staged = vc.stage_rows(tmp_path, [2006], vc.TARGETS)
    remote = {
        "nba_stats_pbp": {
            "play_by_play_2005.parquet": {"size": 100, "updatedAt": "2026-07-24T00:00:00Z"},
            "play_by_play_2005.rds": {"size": 200, "updatedAt": "2026-07-24T00:00:00Z"},
            "nba_play_by_play_2006.parquet": {"size": 1, "updatedAt": "x"},
        }
    }
    manifest = vc.build_manifest(staged, remote, {})
    shadow = vc.shadowed_assets(manifest, remote, vc.TARGETS)
    names = {s["asset"] for s in shadow}
    assert names == {"play_by_play_2005.parquet", "play_by_play_2005.rds"}
    assert "nba_play_by_play_2006.parquet" not in names


def test_render_manifest_names_destroyed_and_collision(tmp_path):
    _stage(tmp_path, 2006)
    staged = vc.stage_rows(tmp_path, [2006], vc.TARGETS)
    remote = {
        "nba_stats_pbp": {
            "nba_play_by_play_2006.parquet": {"size": 1, "updatedAt": "2023-03-30T17:42:36Z"}
        }
    }
    manifest = vc.build_manifest(staged, remote, {})
    text = vc.render_manifest(
        manifest,
        vc.shadowed_assets(manifest, remote, vc.TARGETS),
        seasons=[2006],
        repo="r",
        targets=vc.TARGETS,
        allowlist=set(),
        allowed_findings=[],
        blocking_findings=[],
        execute=False,
    )
    assert "WOULD BE DESTROYED" in text
    assert "nba_play_by_play_2006.parquet" in text
    assert "DRY RUN" in text
    assert "COLLISION" in text  # lineups tag already carries a different dataset
    assert "gate (section 10.3): **PASS**" in text


def test_render_manifest_reports_a_failing_gate_and_lists_blockers(tmp_path):
    _stage(tmp_path, 2006)
    staged = vc.stage_rows(tmp_path, [2006], vc.TARGETS)
    manifest = vc.build_manifest(staged, {}, {})
    blocking = [
        {"season": 2006, "family": "schedule", "verdict": "DIFF", "detail": "score_mismatch=3"}
    ]
    text = vc.render_manifest(
        manifest,
        [],
        seasons=[2006],
        repo="r",
        targets=vc.TARGETS,
        allowlist=set(),
        allowed_findings=[],
        blocking_findings=blocking,
        execute=False,
    )
    assert "FAIL -- PUBLISH BLOCKED" in text
    assert "score_mismatch=3" in text
    assert "no blanket override" in text


# --------------------------------------------------------------------------- gate


def _fake_gate(findings):
    return lambda seasons, staging, repo, raw: (findings, 1 if findings else 0)


def test_check_gate_blocks_on_unexplained_diff(tmp_path, monkeypatch):
    finding = {
        "season": 2011,
        "family": "schedule",
        "verdict": "DIFF",
        "detail": "score_mismatch=4",
    }
    monkeypatch.setattr(v3_gate, "run_gate", _fake_gate([finding]))
    ok, blocking, allowed = vc.check_gate([2011], tmp_path, tmp_path, tmp_path, set())
    assert ok is False and blocking == [finding] and allowed == []


def test_check_gate_allowlist_is_per_season_family(tmp_path, monkeypatch):
    a = {"season": 2011, "family": "schedule", "verdict": "DIFF", "detail": "x"}
    b = {"season": 2012, "family": "schedule", "verdict": "DIFF", "detail": "y"}
    monkeypatch.setattr(v3_gate, "run_gate", _fake_gate([a, b]))

    ok, blocking, allowed = vc.check_gate(
        [2011, 2012], tmp_path, tmp_path, tmp_path, {"2011:schedule"}
    )
    assert ok is False and blocking == [b] and allowed == [a]

    ok, blocking, allowed = vc.check_gate(
        [2011, 2012], tmp_path, tmp_path, tmp_path, {"2011:schedule", "2012:schedule"}
    )
    assert ok is True and blocking == [] and len(allowed) == 2


def test_check_gate_passes_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(
        v3_gate,
        "run_gate",
        _fake_gate([{"season": 2011, "family": "schedule", "verdict": "OK", "detail": ""}]),
    )
    assert vc.check_gate([2011], tmp_path, tmp_path, tmp_path, set())[0] is True


def test_main_refuses_to_publish_when_gate_fails(tmp_path, monkeypatch, capsys):
    _stage(tmp_path / "v3_staging", 2006)
    gh = FakeGh()
    monkeypatch.setattr(vc, "_gh_runner", gh)
    monkeypatch.setattr(
        v3_gate,
        "run_gate",
        _fake_gate([{"season": 2006, "family": "schedule", "verdict": "DIFF", "detail": "boom"}]),
    )

    rc = vc.main(
        [
            "-s",
            "2006",
            "-e",
            "2006",
            "--repo-root",
            str(tmp_path),
            "--staging",
            str(tmp_path / "v3_staging"),
            "--execute",
        ]
    )
    assert rc == 1
    assert "GATE FAILED" in capsys.readouterr().out
    assert gh.uploads() == []  # nothing touched the release

    # ...but the manifest IS written -- the operator needs the blast radius while
    # deciding whether the DIFF is explainable, not only afterwards.
    manifests = list((tmp_path / "logs").glob("v3_cutover_manifest_*.md"))
    assert len(manifests) == 1
    text = manifests[0].read_text(encoding="utf-8")
    assert "FAIL -- PUBLISH BLOCKED" in text and "boom" in text


# --------------------------------------------------------------------------- upload / resume


def test_upload_one_verifies_size_and_writes_receipt(tmp_path):
    staging = tmp_path / "v3_staging"
    _stage(staging, 2006)
    row = vc.build_manifest(vc.stage_rows(staging, [2006], vc.TARGETS), {}, {})[0]
    gh = FakeGh()

    vc.upload_one(row, "repo", staging, runner=gh)
    assert vc.load_receipts(staging)[row["key"]]["sha256"] == row["sha256"]


def test_upload_one_raises_when_asset_is_silently_dropped(tmp_path):
    staging = tmp_path / "v3_staging"
    _stage(staging, 2006)
    row = vc.build_manifest(vc.stage_rows(staging, [2006], vc.TARGETS), {}, {})[0]

    class Dropping(FakeGh):
        def __call__(self, args):
            if args[:2] == ["release", "upload"]:
                self.calls.append(args)
                return ""  # accepted, but never lands
            return super().__call__(args)

    with pytest.raises(RuntimeError, match="silent drop"):
        vc.upload_one(row, "repo", staging, runner=Dropping({"nba_stats_schedules": []}))
    assert vc.load_receipts(staging) == {}


def test_upload_one_raises_on_size_mismatch(tmp_path):
    staging = tmp_path / "v3_staging"
    _stage(staging, 2006)
    row = vc.build_manifest(vc.stage_rows(staging, [2006], vc.TARGETS), {}, {})[0]

    class Truncating(FakeGh):
        def __call__(self, args):
            out = super().__call__(args)
            if args[:2] == ["release", "upload"]:
                self.releases[args[2]][-1]["size"] = 1
            return out

    with pytest.raises(RuntimeError, match="remote size"):
        vc.upload_one(row, "repo", staging, runner=Truncating())


def test_execute_is_resumable_and_idempotent(tmp_path, monkeypatch):
    """Second run uploads nothing: every asset is UNCHANGED via its receipt."""
    staging = tmp_path / "v3_staging"
    _stage(staging, 2006)
    gh = FakeGh()
    monkeypatch.setattr(vc, "_gh_runner", gh)
    monkeypatch.setattr(v3_gate, "run_gate", _fake_gate([]))
    argv = [
        "-s",
        "2006",
        "-e",
        "2006",
        "--repo-root",
        str(tmp_path),
        "--staging",
        str(staging),
        "--families",
        "schedule,play_by_play,possessions",
        "--execute",
    ]

    assert vc.main(argv) == 0
    first = len(gh.uploads())
    assert first == 3

    assert vc.main(argv) == 0
    assert len(gh.uploads()) == first  # no re-upload


def test_execute_stops_on_first_failure_leaving_the_rest_queued(tmp_path, monkeypatch):
    staging = tmp_path / "v3_staging"
    _stage(staging, 2006)

    class FailSecond(FakeGh):
        def __call__(self, args):
            out = super().__call__(args)
            if args[:2] == ["release", "upload"] and len(self.uploads()) == 2:
                self.releases[args[2]][-1]["size"] = 1
            return out

    gh = FailSecond()
    monkeypatch.setattr(vc, "_gh_runner", gh)
    monkeypatch.setattr(v3_gate, "run_gate", _fake_gate([]))
    rc = vc.main(
        [
            "-s",
            "2006",
            "-e",
            "2006",
            "--repo-root",
            str(tmp_path),
            "--staging",
            str(staging),
            "--families",
            "schedule,play_by_play,possessions",
            "--execute",
        ]
    )
    assert rc == 1
    assert len(gh.uploads()) == 2  # stopped, did not push the third
    assert len(vc.load_receipts(staging)) == 1  # only the verified one


# --------------------------------------------------------------------------- safety rails


def test_dry_run_is_the_default_and_uploads_nothing(tmp_path, monkeypatch):
    staging = tmp_path / "v3_staging"
    _stage(staging, 2006)
    gh = FakeGh()
    monkeypatch.setattr(vc, "_gh_runner", gh)
    monkeypatch.setattr(v3_gate, "run_gate", _fake_gate([]))

    rc = vc.main(
        ["-s", "2006", "-e", "2006", "--repo-root", str(tmp_path), "--staging", str(staging)]
    )
    assert rc == 0
    assert gh.uploads() == []
    manifests = list((tmp_path / "logs").glob("v3_cutover_manifest_*.md"))
    assert len(manifests) == 1 and "DRY RUN" in manifests[0].read_text(encoding="utf-8")


def test_execute_refuses_a_colliding_target_tag(tmp_path, monkeypatch, capsys):
    staging = tmp_path / "v3_staging"
    _stage(staging, 2006)
    gh = FakeGh()
    monkeypatch.setattr(vc, "_gh_runner", gh)
    monkeypatch.setattr(v3_gate, "run_gate", _fake_gate([]))

    rc = vc.main(
        [
            "-s",
            "2006",
            "-e",
            "2006",
            "--repo-root",
            str(tmp_path),
            "--staging",
            str(staging),
            "--families",
            "lineups",
            "--execute",
        ]
    )
    assert rc == 1
    assert "REFUSING" in capsys.readouterr().out
    assert gh.uploads() == []


def test_tag_override_clears_the_collision(tmp_path, monkeypatch):
    staging = tmp_path / "v3_staging"
    _stage(staging, 2006)
    gh = FakeGh()
    monkeypatch.setattr(vc, "_gh_runner", gh)
    monkeypatch.setattr(v3_gate, "run_gate", _fake_gate([]))

    rc = vc.main(
        [
            "-s",
            "2006",
            "-e",
            "2006",
            "--repo-root",
            str(tmp_path),
            "--staging",
            str(staging),
            "--families",
            "lineups",
            "--tag",
            "lineups=nba_stats_lineups_pbp",
            "--execute",
        ]
    )
    assert rc == 0
    assert len(gh.uploads()) == 1


def test_retire_tags_is_not_bundled_with_the_upload(tmp_path, monkeypatch):
    staging = tmp_path / "v3_staging"
    _stage(staging, 2006)
    gh = FakeGh({t: [_asset("x.parquet", 5)] for t in vc.RETIRE_TAGS})
    monkeypatch.setattr(vc, "_gh_runner", gh)

    assert (
        vc.main(["--retire-v3-tags", "--repo-root", str(tmp_path), "--staging", str(staging)]) == 0
    )
    assert gh.uploads() == []
    assert set(gh.releases) == set(vc.RETIRE_TAGS)  # dry run deleted nothing

    assert (
        vc.main(
            [
                "--retire-v3-tags",
                "--execute",
                "--repo-root",
                str(tmp_path),
                "--staging",
                str(staging),
            ]
        )
        == 0
    )
    assert gh.releases == {}
    assert gh.uploads() == []


def test_unknown_family_is_rejected(tmp_path):
    assert vc.main(["--families", "nope", "--repo-root", str(tmp_path)]) == 2


def test_tag_override_rejects_a_bad_pair():
    with pytest.raises(SystemExit):
        vc._parse_tag_overrides(["lineups"], vc.TARGETS)
    with pytest.raises(SystemExit):
        vc._parse_tag_overrides(["nope=t"], vc.TARGETS)
