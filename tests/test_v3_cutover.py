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
        pl.DataFrame(
            {
                "game_id": [f"00{i}" for i in range(rows)],
                "pts": list(range(rows)),
                "ok": [True] * rows,
            }
        ).write_parquet(p)
        out[fam] = p
    return out


#: A target that DOES declare a tag collision. No production target does any more
#: (the v3 lineups moved to their own `nba_stats_game_lineups` tag), but the
#: refusal rail still guards any future one, so the test arms it itself.
_COLLIDING = {
    "lineups": vc.Target(
        family="lineups",
        tag="nba_stats_lineups",
        asset="nba_lineups_{season}.parquet",
        collision="nba_stats_lineups carries the season-level leaguedashlineups dataset.",
    )
}


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
        if args[:2] == ["release", "delete-asset"]:
            tag, name = args[2], args[3]
            assets = self.releases.get(tag, [])
            if not any(a["name"] == name for a in assets):
                raise subprocess.CalledProcessError(1, "gh")  # gh errors on a missing asset
            assets[:] = [a for a in assets if a["name"] != name]
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


def test_stage_rows_emits_one_row_per_format(tmp_path):
    """parquet + rds + csv.gz for every family -- hoopR reads the rds."""
    _stage(tmp_path, 2006)
    rows = vc.stage_rows(tmp_path, [2006], vc.TARGETS)
    assert len(rows) == len(vc.TARGETS) * len(vc.FORMATS)
    assert {r["format"] for r in rows} == set(vc.FORMATS)
    pbp = {r["format"]: r["asset"] for r in rows if r["family"] == "play_by_play"}
    assert pbp == {
        "parquet": "nba_play_by_play_2006.parquet",
        "rds": "nba_play_by_play_2006.rds",
        "csv.gz": "nba_play_by_play_2006.csv.gz",
    }
    # every derived asset is a real file with its own hash, not a placeholder row
    assert all(r["path"].exists() and r["size"] > 0 for r in rows)
    assert len({r["sha256"] for r in rows if r["family"] == "play_by_play"}) == 3


def test_stage_rows_can_be_restricted_to_one_format(tmp_path):
    _stage(tmp_path, 2006)
    rows = vc.stage_rows(tmp_path, [2006], vc.TARGETS, formats=("parquet",))
    assert {r["format"] for r in rows} == {"parquet"}


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
    by_key = {(r["family"], r["format"]): r for r in manifest}
    assert by_key[("play_by_play", "parquet")]["verdict"] == "REPLACE"
    assert by_key[("play_by_play", "parquet")]["remote_size"] == 1
    assert by_key[("play_by_play", "parquet")]["remote_updated_at"] == "2023-03-30T17:42:36Z"
    # only the parquet exists remotely; the rds + csv.gz siblings are still NEW
    assert by_key[("play_by_play", "rds")]["verdict"] == "NEW"
    assert by_key[("schedule", "parquet")]["verdict"] == "NEW"
    assert by_key[("schedule", "parquet")]["remote_size"] is None
    assert pbp["asset"] == "nba_play_by_play_2006.parquet"


def test_build_manifest_unchanged_from_receipt(tmp_path):
    _stage(tmp_path, 2006)
    staged = vc.stage_rows(tmp_path, [2006], vc.TARGETS)
    row = next(r for r in staged if r["family"] == "possessions" and r["format"] == "parquet")
    remote = {row["tag"]: {row["asset"]: {"size": row["size"], "updatedAt": "x"}}}
    receipts = {f"{row['tag']}/{row['asset']}": {"sha256": row["sha256"], "size": row["size"]}}

    manifest = vc.build_manifest(staged, remote, receipts)
    got = next(r for r in manifest if r["family"] == "possessions" and r["format"] == "parquet")
    assert got["verdict"] == "UNCHANGED"


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


def test_render_manifest_names_destroyed(tmp_path):
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
    assert "gate (section 9.3): **PASS**" in text
    assert "## Summary per format" in text


# ------------------------------------------------------------------- season-label collision


def test_v3_lineups_get_their_own_tag_and_leave_the_incumbent_alone():
    """Decision 3: the season-level `nba_stats_lineups` dataset is a different dataset."""
    assert vc.TARGETS["lineups"].tag == "nba_stats_game_lineups"
    assert vc.TARGETS["lineups"].legacy_asset is None
    assert not any(t.collision for t in vc.TARGETS.values())


def test_season_label_collision_pairs_the_same_real_season():
    """END-year 1997 and START-year 1996 are the SAME 1996-97 games."""
    remote = {
        "nba_stats_pbp": {
            "play_by_play_1996.parquet": {"size": 100, "updatedAt": "x"},
            "play_by_play_1996.rds": {"size": 200, "updatedAt": "x"},
            "play_by_play_1995.parquet": {"size": 50, "updatedAt": "x"},
        }
    }
    got = vc.season_label_collisions([1997], remote, {"play_by_play": vc.TARGETS["play_by_play"]})
    assert len(got) == 1
    (row,) = got
    assert row["season"] == 1997
    assert row["new_stem"] == "nba_play_by_play_1997"
    assert row["legacy_assets"] == ["play_by_play_1996.parquet", "play_by_play_1996.rds"]
    assert row["legacy_bytes"] == 300


def test_season_label_collision_ignores_an_unpublished_legacy_name(tmp_path):
    """A name nobody can fetch is not a collision anyone can hit."""
    assert vc.season_label_collisions([1997], {"nba_stats_pbp": {}}, vc.TARGETS) == []


def test_manifest_carries_the_season_label_collision_section(tmp_path):
    _stage(tmp_path, 1997)
    remote = {"nba_stats_pbp": {"play_by_play_1996.parquet": {"size": 100, "updatedAt": "x"}}}
    staged = vc.stage_rows(tmp_path, [1997], vc.TARGETS)
    manifest = vc.build_manifest(staged, remote, {})
    text = vc.render_manifest(
        manifest,
        [],
        seasons=[1997],
        repo="r",
        targets=vc.TARGETS,
        allowlist=set(),
        allowed_findings=[],
        blocking_findings=[],
        execute=False,
        collisions=vc.season_label_collisions([1997], remote, vc.TARGETS),
    )
    assert "SEASON-LABEL COLLISION" in text
    assert "play_by_play_1996.parquet" in text
    assert "nba_play_by_play_1997" in text
    assert "1996-97" in text


def test_tag_readme_names_both_patterns_and_the_winner():
    text = vc.render_tag_readme("nba_stats_pbp", vc.TARGETS, [1997, 1998])
    assert "nba_play_by_play_1998" in text and "play_by_play_1997" in text
    assert "AUTHORITATIVE" in text
    assert "scheduled for removal" in text
    assert "END year" in text and "START year" in text
    assert ".rds" in text


def test_dry_run_writes_the_readme_locally_but_uploads_nothing(tmp_path):
    staging = tmp_path / "v3_staging"
    staging.mkdir(parents=True)
    gh = FakeGh()
    vc.upload_readmes(
        ["nba_stats_pbp"], vc.TARGETS, [1997], "repo", staging, runner=gh, execute=False
    )
    assert gh.uploads() == []
    assert (vc.release_build_dir(staging) / "nba_stats_pbp" / "README.md").exists()


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


def test_manifest_carries_the_reason_and_flags_an_unattributed_allowlist(tmp_path):
    _stage(tmp_path, 2006)
    staged = vc.stage_rows(tmp_path, [2006], vc.TARGETS)
    allowed = [
        {"season": 2006, "family": "schedule", "verdict": "DIFF", "detail": "score_mismatch=1"},
        {"season": 2006, "family": "play_by_play", "verdict": "DIFF", "detail": "score_mismatch=1"},
    ]
    text = vc.render_manifest(
        vc.build_manifest(staged, {}, {}),
        [],
        seasons=[2006],
        repo="r",
        targets=vc.TARGETS,
        allowlist={"2006:schedule", "2006:play_by_play"},
        allowed_findings=allowed,
        blocking_findings=[],
        execute=False,
        reasons={"2006:schedule": "raw leaguegamelog agrees with v3"},
    )
    assert "raw leaguegamelog agrees with v3" in text
    # the entry given no reason must not read as explained
    assert "UNATTRIBUTED" in text


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


def test_allow_diff_file_explains_the_finding_and_unblocks_it(tmp_path, monkeypatch):
    _stage(tmp_path / "v3_staging", 2006)
    monkeypatch.setattr(vc, "_gh_runner", FakeGh())
    monkeypatch.setattr(
        v3_gate,
        "run_gate",
        _fake_gate([{"season": 2006, "family": "schedule", "verdict": "DIFF", "detail": "boom"}]),
    )
    allowfile = tmp_path / "allow.txt"
    allowfile.write_text(
        "# a comment\n\n2006:schedule=raw leaguegamelog agrees with v3\n", encoding="utf-8"
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
            "--allow-diff-file",
            str(allowfile),
        ]
    )
    assert rc == 0  # the explained DIFF no longer blocks
    text = next((tmp_path / "logs").glob("v3_cutover_manifest_*.md")).read_text(encoding="utf-8")
    assert "raw leaguegamelog agrees with v3" in text
    assert "UNATTRIBUTED" not in text
    assert "a comment" not in text  # comments are not entries


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
    # 3 families x 3 formats, plus one README per touched tag (3 tags)
    assert len(gh.uploads()) == 12

    assert vc.main(argv) == 0
    # data assets are all UNCHANGED on the second pass; only the READMEs re-upload
    assert len(gh.uploads()) == 15


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
    monkeypatch.setattr(vc, "TARGETS", _COLLIDING)
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
    monkeypatch.setattr(vc, "TARGETS", _COLLIDING)
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
    # 3 formats + the generated per-tag README
    assert len(gh.uploads()) == 4


# --------------------------------------------------------------------- retire legacy assets


def _published(tmp_path, monkeypatch, gh, *, seasons=(2006,), families="play_by_play"):
    """Run a full --execute publish against the fake release; return the staging dir."""
    staging = tmp_path / "v3_staging"
    for s in seasons:
        _stage(staging, s)
    monkeypatch.setattr(vc, "_gh_runner", gh)
    monkeypatch.setattr(v3_gate, "run_gate", _fake_gate([]))
    rc = vc.main(
        [
            "-s",
            str(min(seasons)),
            "-e",
            str(max(seasons)),
            "--repo-root",
            str(tmp_path),
            "--staging",
            str(staging),
            "--families",
            families,
            "--execute",
        ]
    )
    assert rc == 0
    return staging


def test_retire_legacy_refuses_when_the_replacement_was_never_published(tmp_path, monkeypatch):
    """The legacy bytes are the ONLY copy until the replacement verifies. Never delete first."""
    staging = tmp_path / "v3_staging"
    _stage(staging, 2006)
    gh = FakeGh({"nba_stats_pbp": [_asset("play_by_play_2005.parquet", 100)]})
    monkeypatch.setattr(vc, "_gh_runner", gh)

    rc = vc.main(
        [
            "--retire-legacy-assets",
            "-s",
            "2006",
            "-e",
            "2006",
            "--repo-root",
            str(tmp_path),
            "--staging",
            str(staging),
            "--families",
            "play_by_play",
            "--execute",
        ]
    )
    assert rc == 1
    assert gh.releases["nba_stats_pbp"] == [_asset("play_by_play_2005.parquet", 100)]


def test_retire_legacy_refuses_when_only_some_formats_verify(tmp_path, monkeypatch):
    """hoopR reads the .rds -- a verified parquet alone must not retire the season."""
    gh = FakeGh({"nba_stats_pbp": [_asset("play_by_play_2005.parquet", 100)]})
    staging = _published(tmp_path, monkeypatch, gh)

    # forget the rds receipt: that format is no longer provably on the release
    receipts = vc.load_receipts(staging)
    del receipts["nba_stats_pbp/nba_play_by_play_2006.rds"]
    vc.receipts_path(staging).write_text(json.dumps(receipts))

    rc = vc.main(
        [
            "--retire-legacy-assets",
            "-s",
            "2006",
            "-e",
            "2006",
            "--repo-root",
            str(tmp_path),
            "--staging",
            str(staging),
            "--families",
            "play_by_play",
            "--execute",
        ]
    )
    assert rc == 1
    assert any(a["name"] == "play_by_play_2005.parquet" for a in gh.releases["nba_stats_pbp"])


def test_retire_legacy_deletes_once_every_format_verifies(tmp_path, monkeypatch):
    gh = FakeGh(
        {
            "nba_stats_pbp": [
                _asset("play_by_play_2005.parquet", 100),
                _asset("play_by_play_2005.rds", 200),
                _asset("play_by_play_2005.csv.gz", 50),
            ]
        }
    )
    staging = _published(tmp_path, monkeypatch, gh)
    argv = [
        "--retire-legacy-assets",
        "-s",
        "2006",
        "-e",
        "2006",
        "--repo-root",
        str(tmp_path),
        "--staging",
        str(staging),
        "--families",
        "play_by_play",
    ]

    assert vc.main(argv) == 0  # dry run
    assert (
        sum(1 for a in gh.releases["nba_stats_pbp"] if a["name"].startswith("play_by_play_")) == 3
    )

    assert vc.main(argv + ["--execute"]) == 0
    names = {a["name"] for a in gh.releases["nba_stats_pbp"]}
    assert not any(n.startswith("play_by_play_2005") for n in names)
    assert "nba_play_by_play_2006.rds" in names  # the replacement is untouched


def test_retire_legacy_is_never_bundled_with_an_upload_or_with_tag_retirement(
    tmp_path, monkeypatch
):
    staging = tmp_path / "v3_staging"
    _stage(staging, 2006)
    gh = FakeGh({"nba_stats_pbp": [_asset("play_by_play_2005.parquet", 100)]})
    monkeypatch.setattr(vc, "_gh_runner", gh)
    monkeypatch.setattr(v3_gate, "run_gate", _fake_gate([]))

    # never uploads
    vc.main(
        [
            "--retire-legacy-assets",
            "-s",
            "2006",
            "-e",
            "2006",
            "--repo-root",
            str(tmp_path),
            "--staging",
            str(staging),
            "--families",
            "play_by_play",
        ]
    )
    assert gh.uploads() == []

    # and cannot be combined with _v3 tag retirement
    assert (
        vc.main(
            [
                "--retire-legacy-assets",
                "--retire-v3-tags",
                "--repo-root",
                str(tmp_path),
                "--staging",
                str(staging),
            ]
        )
        == 2
    )


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
