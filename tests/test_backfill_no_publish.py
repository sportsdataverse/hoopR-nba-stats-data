"""The league-dash backfill runner must carry no upload path at all.

It used to pass ``--publish`` unconditionally and upload after every season, so
anyone running a backfill rewrote a live release as a side effect. An opt-in
flag was rejected as the fix: a flag can be typed by accident or copied out of a
runbook line. These assertions pin the stronger property -- the script has no
code path that publishes, and asking it to publish is a usage error.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "leaguedash_backfill.sh"


def _code_lines() -> list[str]:
    """Script lines that can act, with comments and `echo` output dropped.

    The header documents the deliberate publish invocation on purpose and the
    run banner prints it for the operator, so a flat substring search over the
    whole file would match prose rather than behaviour. What must stay clean is
    every line that actually runs something.
    """
    out = []
    for line in SCRIPT.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "echo ")):
            out.append(stripped)
    return out


def test_no_publish_flag_in_executable_lines():
    offenders = [ln for ln in _code_lines() if "--publish" in ln]
    assert not offenders, f"backfill script reaches a publish path: {offenders}"


def test_no_upload_command_in_executable_lines():
    offenders = [
        ln
        for ln in _code_lines()
        if "gh release" in ln or "upload_artifacts" in ln or "git push" in ln
    ]
    assert not offenders, f"backfill script uploads directly: {offenders}"


def test_dry_run_is_the_only_publish_adjacent_mode():
    """`-n` plans uploads; nothing else may set the CLI flag the script passes."""
    values = re.findall(r'\bPUBLISH="([^"]*)"', SCRIPT.read_text(encoding="utf-8"))
    assert values, "expected a PUBLISH= variable driving the CLI flag"
    assert set(values) <= {"", "--dry-run"}, (
        f"PUBLISH is set to something other than empty or --dry-run: {values}"
    )


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
def test_publish_flag_is_rejected():
    """`-p` is not merely absent -- getopts refuses it before any work happens."""
    proc = subprocess.run(
        [shutil.which("bash"), str(SCRIPT), "-p"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 2, f"expected usage exit 2, got {proc.returncode}: {proc.stderr}"
    assert "usage:" in proc.stderr


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
@pytest.mark.parametrize("args", [["-s", "20x0"], ["-s", "2020", "-e", "2019"]])
def test_unusable_season_range_is_rejected(args):
    """An empty `seq` range would build nothing and still report EXIT=0."""
    proc = subprocess.run(
        [shutil.which("bash"), str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 2, f"expected exit 2, got {proc.returncode}: {proc.stdout}"
    assert "::error ::" in proc.stderr
