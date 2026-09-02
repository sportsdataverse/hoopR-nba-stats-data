"""`nba_model_publish impact` must not publish unless asked, and the cron must ask.

`impact` used to call ``upload_artifacts`` unconditionally: publishing was the
default and ``--dry-run`` was the only way out, so any ad-hoc or exploratory
build rewrote a live release as a side effect.

The obvious fix -- make it build-only, like the league-dash backfill runner --
would have been worse here, because this publisher IS wired: a daily droplet
cron exists to publish `nba_player_impact` (scripts/P0_DROPLET_RUNBOOK.md §6).
Silently demoting it to a build would have turned a multi-hour job into a
no-op that still exits 0.

So the guard is two-sided, and both sides are pinned below:
  * the CLI default reaches no upload path at all, and
  * every wired invocation passes `--publish`.

Dropping either half re-opens one of the two failure modes.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import nba_model_publish.cli as cli
import pytest
from nba_model_publish.cli import main

REPO = Path(__file__).resolve().parents[1]
RUNBOOK = REPO / "scripts" / "P0_DROPLET_RUNBOOK.md"
HANDOFF = REPO / "docs" / "WARM_HANDOFF.md"
LAUNCHER = REPO / "scripts" / "run_impact_backfill.sh"
WORKFLOW = REPO / ".github" / "workflows" / "nba_models.yml"


def _read(path: Path) -> str:
    """Read a pinned file, failing with the reason rather than a bare OSError.

    CI sparse-checkouts the repo, so a file this module asserts on can simply
    not be present -- which would surface as an inscrutable FileNotFoundError
    (it did, for `.github`, on the first run of this suite). Name the fix.
    """
    assert path.exists(), (
        f"{path.relative_to(REPO)} is missing -- if this is CI, add its top-level "
        "directory to the sparse-checkout in .github/workflows/tests.yml. "
        "Do not skip: an unread file is an unproven guard."
    )
    return path.read_text(encoding="utf-8")


@pytest.fixture
def impact_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Callable[..., list[bool]]:
    """Run `impact` with the builder stubbed and every upload recorded, not performed.

    Returns a callable taking the extra CLI flags and returning the list of
    ``dry_run`` values ``upload_artifacts`` was called with -- empty list means
    the upload path was never reached.
    """
    monkeypatch.setattr(
        "nba_model_publish.builders.build_nba_player_impact",
        lambda *a, **k: [{"season": 2024, "rows": 3}],
    )
    monkeypatch.setattr(cli, "_resolve_proxy_provider", lambda *a, **k: None)

    calls: list[bool] = []

    def _fake_upload(*args: Any, dry_run: bool = False, **kwargs: Any) -> dict[str, Any]:
        calls.append(dry_run)
        return {"uploaded": 0 if dry_run else 1, "files": ["x"], "failed": []}

    monkeypatch.setattr(cli, "upload_artifacts", _fake_upload)

    # The publish floors run against the BUILT assets; this builder is stubbed
    # and writes none, so record the gate call instead of evaluating it. The
    # gate's own teeth live in tests/test_impact_gates.py; what matters here is
    # that it is reached, which `gate_calls` below pins.
    gate_calls: list[list[int]] = []
    monkeypatch.setattr(
        cli, "check_publish_floors", lambda out, seasons, **kw: gate_calls.append(list(seasons))
    )
    cli._gate_calls_for_tests = gate_calls

    def run(*extra: str) -> list[bool]:
        calls.clear()
        rc = main(["impact", "--seasons", "2024", "--out", str(tmp_path), *extra])
        assert rc == 0
        return list(calls)

    return run


# --- the default is non-publishing -------------------------------------------


def test_default_never_reaches_the_upload_path(
    impact_run: Callable[..., list[bool]], capsys: pytest.CaptureFixture[str]
) -> None:
    """No flags: `upload_artifacts` is not called at all -- not even with dry_run=True."""
    assert impact_run() == []
    assert "publish: skipped" in capsys.readouterr().out


def test_default_is_not_merely_a_dry_run_upload(impact_run: Callable[..., list[bool]]) -> None:
    """Pinned separately: passing dry_run=True to the uploader would also 'not publish',
    but it still enumerates the release. The default must not touch it at all."""
    assert not impact_run(), "the default must reach zero upload calls, not a dry one"


# --- the publishing paths still publish --------------------------------------


def test_publish_flag_performs_the_upload(impact_run: Callable[..., list[bool]]) -> None:
    """The cron's flag: both upload calls (seasons + model card) run for real."""
    assert impact_run("--publish") == [False, False]


def test_dry_run_plans_the_upload_without_performing_it(
    impact_run: Callable[..., list[bool]],
) -> None:
    assert impact_run("--dry-run") == [True, True]


def test_dry_run_wins_over_publish(impact_run: Callable[..., list[bool]]) -> None:
    """Two flags, one rule: --dry-run is the stronger one, so a pasted-in
    --publish alongside it cannot upgrade the run into a real publish."""
    assert impact_run("--publish", "--dry-run") == [True, True]


# --- the wired invocations pass it -------------------------------------------


def _cron_lines(path: Path) -> list[str]:
    return [
        ln
        for ln in _read(path).splitlines()
        if "run_impact_backfill.sh" in ln and ln.lstrip().startswith("30 9 ")
    ]


@pytest.mark.parametrize("doc", [RUNBOOK, HANDOFF], ids=["runbook", "handoff"])
def test_documented_cron_still_publishes(doc: Path) -> None:
    """The whole point of the daily cron is publishing. A cron line without
    --publish runs for hours, logs EXIT=0, and writes nothing."""
    lines = _cron_lines(doc)
    assert lines, f"no impact cron line found in {doc.name} -- did it move?"
    for ln in lines:
        assert "--publish" in ln, f"{doc.name} cron line no longer publishes: {ln}"


def test_launcher_forwards_extra_flags_to_the_cli() -> None:
    """`--publish` only reaches the CLI because the launcher forwards "$@"."""
    body = _read(LAUNCHER)
    assert '"$@"' in body, "run_impact_backfill.sh stopped forwarding extra args"


def test_workflow_flags_follow_the_subcommand() -> None:
    """--repo/--dry-run/--publish belong to the `impact` subparser. They once
    preceded `impact`, which argparse rejects outright."""
    body = _read(WORKFLOW)
    run_block = body[body.index("uv run --no-sync python -m nba_model_08_impact") :]
    assert re.match(r"uv run --no-sync python -m nba_model_08_impact\b", run_block)
    for flag in ("--publish", "--dry-run"):
        assert flag in run_block, f"workflow lost {flag}"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_launcher_is_syntactically_valid() -> None:
    assert subprocess.run([shutil.which("bash"), "-n", str(LAUNCHER)], timeout=60).returncode == 0


# --- the gate runs before anything is uploaded ---------------------------------


def test_the_publish_floors_run_on_every_invocation(impact_run: Callable[..., list[bool]]) -> None:
    """Including the non-publishing default: a build whose gates fail must be
    visible in the run that produced it, not first at upload time."""
    impact_run()
    assert cli._gate_calls_for_tests == [[2024]]
    impact_run("--publish")
    assert cli._gate_calls_for_tests[-1] == [2024]
