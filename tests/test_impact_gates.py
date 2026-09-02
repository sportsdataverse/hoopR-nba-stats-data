"""Publish floors + the SPM coefficient sidecar (hermetic — no network, no model compute).

The floors themselves were derived from the real published release (see
``nba_model_publish/gates.py``); these tests pin the MACHINERY: a degraded
build fails, an uncomputable metric is SKIPPED rather than PASS, and the
gate blocks the publish path instead of merely printing.
"""

from __future__ import annotations

import json

import numpy as np
import polars as pl
import pytest
from nba_model_publish import gates as G
from nba_model_publish.builders import SPM_SIDECAR_NAME, write_spm_coefficients

_SKILL = np.random.default_rng(11).normal(0, 2.0, 500)


def _season(season: int, *, noise: float = 0.25, seed: int = 0) -> pl.DataFrame:
    """A season whose engines agree strongly and whose players persist across seasons.

    One shared latent skill vector across seasons is what makes the forward
    gates (RAPM year-over-year, DARKO forward) computable at all — regenerating
    skill per season would model a league of strangers.
    """
    n = len(_SKILL)
    rng = np.random.default_rng(seed + season)

    def jit(scale):
        return _SKILL + rng.normal(0, scale, n)

    return pl.DataFrame(
        {
            "player_id": pl.Series(np.arange(1, n + 1), dtype=pl.Int64),
            "season": pl.Series([season] * n, dtype=pl.Int64),
            "season_type": ["Regular Season"] * n,
            "rapm": jit(noise),
            "adj_rapm": jit(noise),
            "spm": jit(noise),
            "darko_projected_rating": jit(noise),
            "min": rng.uniform(200, 2500, n),
        }
    )


def _frames(seasons=(2023, 2024)) -> dict[int, pl.DataFrame]:
    return {s: _season(s) for s in seasons}


def _status(report: dict, gate: str) -> str:
    return next(c["status"] for c in report["checks"] if c["gate"] == gate)


def test_a_healthy_build_passes_every_internal_floor():
    report = G.gate_report(_frames())
    internal = [c for c in report["checks"] if not c["gate"].startswith("oracle_")]
    assert [c["status"] for c in internal] == ["PASS"] * len(internal), report["checks"]


def test_a_degraded_engine_fails_rather_than_passing_quietly():
    """Shuffling adj_rapm breaks its agreement with RAPM — the gate must catch it."""
    frames = _frames()
    frames[2024] = frames[2024].with_columns(pl.col("adj_rapm").shuffle(seed=7))
    report = G.gate_report(frames)
    assert _status(report, "r_rapm_adj_min") == "FAIL"


def test_an_uncomputable_metric_is_skipped_not_passed():
    """One season has no t+1, so the forward gates cannot be evaluated at all.

    SKIPPED must never read as PASS: a single-season invocation would otherwise
    "pass" the DARKO forward floor without measuring anything.
    """
    report = G.gate_report(_frames(seasons=(2024,)))
    assert _status(report, "r_darko_fwd_min") == "SKIPPED"
    assert _status(report, "r_rapm_yoy_min") == "SKIPPED"
    assert report["oracle"]["status"] == "SKIPPED"


def test_oracle_gates_are_skipped_when_the_csvs_are_absent(tmp_path):
    report = G.gate_report(_frames(), oracle_dir=tmp_path)
    assert _status(report, "oracle_rapm_r_min") == "SKIPPED"


def test_check_publish_floors_blocks_and_records_in_the_card(tmp_path):
    frames = _frames()
    frames[2024] = frames[2024].with_columns(pl.col("adj_rapm").shuffle(seed=7))
    for season, frame in frames.items():
        frame.write_parquet(tmp_path / f"{G.TAG}_{season}.parquet")
    card = tmp_path / f"{G.TAG}_card.json"
    card.write_text(json.dumps({"dataset": G.TAG}), encoding="utf-8")

    with pytest.raises(SystemExit, match="publish BLOCKED"):
        G.check_publish_floors(tmp_path, frames)

    recorded = json.loads(card.read_text(encoding="utf-8"))["publish_gates"]
    assert recorded["seasons_gated"] == [2023, 2024]
    assert any(c["status"] == "FAIL" for c in recorded["checks"])


def test_every_floor_has_a_gate_and_every_gate_a_floor():
    """A floor nobody evaluates is decoration; a gate with no floor never blocks."""
    evaluated = {c["gate"] for c in G.gate_report(_frames())["checks"]}
    assert evaluated == set(G.FLOORS)


def test_release_gates_refuse_a_partial_season_set(monkeypatch):
    """A missing release asset must raise, not silently shorten the gated season set.

    A dropped season leaves its forward gates SKIPPED, and SKIPPED is not a FAIL, so the
    CLI would have exited 0 on a season it never actually evaluated.
    """

    import io as _io
    import sys
    import types

    buf = _io.BytesIO()
    pl.DataFrame({"player_id": [1]}).write_parquet(buf)
    ok_bytes = buf.getvalue()

    class _Resp:
        def __init__(self, code):
            self.status_code = code
            self.content = ok_bytes if code == 200 else b""

    stub = types.ModuleType("requests")
    stub.get = lambda url, **kw: _Resp(200 if url.endswith("_2024.parquet") else 404)
    monkeypatch.setitem(sys.modules, "requests", stub)
    with pytest.raises(SystemExit, match="2025 .HTTP 404."):
        G.load_frames_from_release([2024, 2025])


def test_the_build_path_record_declares_the_reproduction_fields(tmp_path):
    """One sidecar schema whichever path wrote it.

    spm_coefficients_from_frames adds reproduces_published_spm_*; the build path could
    not, so a publish from the build path replaced the documented artifact with a record
    missing two keys. They are declared null there instead -- null = not applicable
    (these coefficients ARE the release being produced), never "check passed".
    """
    from types import SimpleNamespace

    from nba_model_publish.builders import spm_coefficient_record

    coef = SimpleNamespace(
        feature_names=["pts", "ast"],
        o_coef=[0.11, 0.07],
        d_coef=[-0.01, 0.02],
        o_intercept=-3.0,
        d_intercept=1.0,
    )
    bf = pl.DataFrame({"player_id": [1, 2, 3], "pts": [20.0, 10.0, 5.0], "ast": [5.0, 3.0, 1.0]})
    spm = pl.DataFrame({"player_id": [1, 2, 3], "spm": [3.0, 0.5, -2.0]})
    rapm = pl.DataFrame({"player_id": [1, 2, 3], "rapm": [2.8, 0.4, -1.9]})
    rec = spm_coefficient_record(2024, coef, bf, spm, rapm)
    assert rec["reproduces_published_spm_r"] is None
    assert rec["reproduces_published_spm_max_abs_diff"] is None


def test_spm_sidecar_round_trips_with_the_fields_the_writeup_reads(tmp_path):
    record = {
        "season": 2024,
        "feature_names": ["pts", "ast"],
        "feature_sd": [8.0, 4.0],
        "o_coef": [0.11, 0.07],
        "d_coef": [-0.01, 0.02],
        "o_intercept": -3.0,
        "d_intercept": 1.0,
        "train_r_spm_vs_rapm": 0.42,
    }
    path = write_spm_coefficients(tmp_path, [record])
    assert path.name == SPM_SIDECAR_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["seasons"] == [2024]
    got = payload["records"][0]
    assert (
        len(got["o_coef"])
        == len(got["d_coef"])
        == len(got["feature_names"])
        == len(got["feature_sd"])
    )
