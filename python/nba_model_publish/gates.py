"""Publish floors for ``nba_player_impact`` — the numeric gates the registry listed as TODO.

Every floor below was derived from an OBSERVED value on real published data
(the 2026-07-29 publish, evaluated 2026-09-01 with
``python -m nba_model_publish gates --from-release``) and sits strictly below
it, so the gate detects a regression without inviting a silently degraded
model. Never lower a floor to make a publish pass — debug the build; a
re-derivation must state the new observation next to the constant.

Two families:

* **internal** — computed from the built per-season frames alone, so they run
  on every publish path (droplet included) and are publish-blocking:
  regular-season population, RAPM ↔ adj-RAPM agreement (the prior shrinks, it
  does not overwrite), the SPM in-sample fit on its own RAPM target, RAPM
  year-over-year reliability and the DARKO forward correlation (the last two
  need two adjacent seasons in the invocation — trailing seasons are already
  mandatory for DARKO).
* **oracle** — concurrent validity against the published Ryan Davis
  single-season RAPM (``rapm_ryan_davis.csv``) with the minutes-played
  baseline, plus Dunks & Threes EPM (recorded, not gated: two seasons is too
  thin to set a floor from). Runs only when ``SDV_PY_NBA_ORACLE_DIR`` (or
  ``--oracle-dir``) holds the CSVs; otherwise reported as SKIPPED, never PASS.
"""

from __future__ import annotations

import io
import json
import math
import os
from pathlib import Path
from typing import Iterable, Optional

import polars as pl

TAG = "nba_player_impact"
RELEASE_BASE = f"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/{TAG}"
ORACLE_DIR_ENV = "SDV_PY_NBA_ORACLE_DIR"
RAPM_ORACLE_FILE = "rapm_ryan_davis.csv"
EPM_ORACLE_FILES = {2025: "2025_EPM_data.csv", 2026: "2026_EPM_data.csv"}

#: gate -> floor. Every floor sits strictly BELOW the value observed on the
#: 2026-07-29 published release (all 30 seasons, 1997-2026), measured
#: 2026-09-01 by ``python -m nba_model_publish gates --from-release
#: --oracle-dir <ClaudeCowork/nba_data/data_metrics>``; the comment records the
#: observation that set it. Never lower one to make a publish pass.
FLOORS: dict[str, Optional[float]] = {
    "rs_rows_min": 400,  # observed min 428 (2003); max 605 (2022)
    "r_rapm_adj_min": 0.75,  # observed min 0.806 (2013); 0.913 in 2026
    "r_spm_rapm_min": 0.22,  # observed min 0.264 (1999); median ~0.43
    "r_rapm_yoy_min": 0.24,  # observed min 0.289 (2020->2021, the bubble pair)
    "r_darko_fwd_min": 0.20,  # observed min 0.242 (2020); n-weighted mean 0.362
    "oracle_rapm_r_min": 0.90,  # observed min 0.948 (2014) over 14 oracle seasons 2010-2023
    "oracle_rapm_beat_minutes_min": 0.50,  # observed min +0.602 (2015); mean +0.65
}

_INTERNAL_GATES = (
    "rs_rows_min",
    "r_rapm_adj_min",
    "r_spm_rapm_min",
    "r_rapm_yoy_min",
    "r_darko_fwd_min",
)
_ORACLE_GATES = ("oracle_rapm_r_min", "oracle_rapm_beat_minutes_min")


def _pearson(df: pl.DataFrame, a: str, b: str) -> Optional[float]:
    sub = df.select(a, b).drop_nulls()
    if sub.height < 3:
        return None
    r = sub.select(pl.corr(a, b)).item()
    return None if r is None or math.isnan(r) else float(r)


def _rs(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.filter(pl.col("season_type") == "Regular Season")


def internal_metrics(frames: dict[int, pl.DataFrame]) -> dict[str, dict]:
    """Per-season internal diagnostics on the Regular Season rows.

    ``frames`` maps the END year to that season's impact frame. Adjacent
    seasons present in ``frames`` also get the forward pair metrics
    (``r_rapm_yoy`` = RAPM(t) vs RAPM(t+1); ``r_darko_fwd`` = projection made
    in t vs realized RAPM in t+1), keyed on t.
    """
    out: dict[str, dict] = {}
    for season in sorted(frames):
        rs = _rs(frames[season])
        row = {
            "rs_rows": rs.height,
            "r_rapm_adj": _pearson(rs, "rapm", "adj_rapm"),
            "r_spm_rapm": _pearson(rs, "spm", "rapm"),
            "r_rapm_yoy": None,
            "r_darko_fwd": None,
            "n_fwd": 0,
        }
        nxt = frames.get(season + 1)
        if nxt is not None:
            pair = rs.select("player_id", "rapm", "darko_projected_rating").join(
                _rs(nxt).select("player_id", pl.col("rapm").alias("next_rapm")),
                on="player_id",
                how="inner",
            )
            row["r_rapm_yoy"] = _pearson(pair, "rapm", "next_rapm")
            row["r_darko_fwd"] = _pearson(pair, "darko_projected_rating", "next_rapm")
            row["n_fwd"] = pair.drop_nulls().height
        out[str(season)] = row
    return out


def _oracle_end_year(label: str) -> Optional[int]:
    # "2009-10" -> 2010 (END year, the frames' season convention)
    return int(label[:4]) + 1 if len(label) >= 4 and label[:4].isdigit() else None


def oracle_metrics(frames: dict[int, pl.DataFrame], oracle_dir: Path) -> dict:
    """Concurrent validity vs the published oracles that ``oracle_dir`` holds."""
    from sportsdataverse.nba.nba_oracle_data import load_epm, load_rapm_ryan_davis

    res: dict = {"dir": str(oracle_dir), "rapm": {}, "epm": {}}
    rapm_path = oracle_dir / RAPM_ORACLE_FILE
    if rapm_path.is_file():
        oracle = load_rapm_ryan_davis(str(rapm_path)).with_columns(
            pl.col("season").map_elements(_oracle_end_year, return_dtype=pl.Int64).alias("end_year")
        )
        for season in sorted(frames):
            o = oracle.filter(pl.col("end_year") == season).select(
                "player_id", pl.col("RAPM").alias("oracle_rapm")
            )
            if o.height == 0:
                continue
            rs = _rs(frames[season]).select("player_id", "rapm", "adj_rapm", "min")
            assert rs.schema["player_id"] == o.schema["player_id"] == pl.Int64
            m = rs.join(o, on="player_id", how="inner")
            r_rapm, r_min = _pearson(m, "rapm", "oracle_rapm"), _pearson(m, "min", "oracle_rapm")
            res["rapm"][str(season)] = {
                "n": m.height,
                "coverage_pct": round(100.0 * m.height / max(rs.height, 1), 1),
                "r_rapm": r_rapm,
                "r_adj_rapm": _pearson(m, "adj_rapm", "oracle_rapm"),
                "r_minutes": r_min,
                "beat_minutes": (r_rapm - r_min)
                if r_rapm is not None and r_min is not None
                else None,
            }
    for season, name in EPM_ORACLE_FILES.items():
        path = oracle_dir / name
        if season in frames and path.is_file():
            o = load_epm(str(path)).select("player_id", "epm")
            rs = _rs(frames[season]).select("player_id", "rapm", "adj_rapm", "min")
            assert rs.schema["player_id"] == o.schema["player_id"] == pl.Int64
            m = rs.join(o, on="player_id", how="inner")
            res["epm"][str(season)] = {
                "n": m.height,
                "r_rapm": _pearson(m, "rapm", "epm"),
                "r_adj_rapm": _pearson(m, "adj_rapm", "epm"),
                "r_minutes": _pearson(m, "min", "epm"),
            }
    return res


def _min_of(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return min(vals) if vals else None


def gate_report(frames: dict[int, pl.DataFrame], *, oracle_dir: Optional[Path] = None) -> dict:
    """Compute every diagnostic and evaluate it against ``FLOORS``.

    Pure computation: never raises on a failing gate (the caller decides), and
    a metric that cannot be computed from the frames given (a single season has
    no forward pair) is SKIPPED, which is not PASS.
    """
    seasons = internal_metrics(frames)
    per = seasons.values()
    summary: dict[str, Optional[float]] = {
        "rs_rows_min": _min_of(r["rs_rows"] for r in per),
        "r_rapm_adj_min": _min_of(r["r_rapm_adj"] for r in per),
        "r_spm_rapm_min": _min_of(r["r_spm_rapm"] for r in per),
        "r_rapm_yoy_min": _min_of(r["r_rapm_yoy"] for r in per),
        "r_darko_fwd_min": _min_of(r["r_darko_fwd"] for r in per),
    }
    fwd = [
        (r["r_darko_fwd"], r["n_fwd"]) for r in per if r["r_darko_fwd"] is not None and r["n_fwd"]
    ]
    summary["r_darko_fwd_wmean"] = (
        (sum(r * n for r, n in fwd) / sum(n for _, n in fwd)) if fwd else None
    )

    oracle: dict = {
        "status": "SKIPPED",
        "reason": f"{ORACLE_DIR_ENV} unset / no {RAPM_ORACLE_FILE}",
    }
    if oracle_dir is not None and (Path(oracle_dir) / RAPM_ORACLE_FILE).is_file():
        oracle = oracle_metrics(frames, Path(oracle_dir))
        oracle["status"] = "RAN" if oracle["rapm"] else "SKIPPED"
        if not oracle["rapm"]:
            oracle["reason"] = (
                "oracle covers none of the seasons built (Ryan Davis RAPM starts 2009-10)"
            )
        summary["oracle_rapm_r_min"] = _min_of(r["r_rapm"] for r in oracle["rapm"].values())
        summary["oracle_rapm_beat_minutes_min"] = _min_of(
            r["beat_minutes"] for r in oracle["rapm"].values()
        )
    else:
        summary["oracle_rapm_r_min"] = None
        summary["oracle_rapm_beat_minutes_min"] = None

    checks = []
    for gate in (*_INTERNAL_GATES, *_ORACLE_GATES):
        floor, observed = FLOORS[gate], summary.get(gate)
        if floor is None or observed is None:
            status = "SKIPPED"
        else:
            status = "PASS" if observed >= floor else "FAIL"
        checks.append({"gate": gate, "floor": floor, "observed": observed, "status": status})
    return {"seasons": seasons, "summary": summary, "oracle": oracle, "checks": checks}


def format_report(report: dict) -> str:
    lines = [f"{'gate':32s} {'floor':>8s} {'observed':>10s}  status"]
    for c in report["checks"]:
        obs = "—" if c["observed"] is None else f"{c['observed']:.3f}"
        floor = "—" if c["floor"] is None else f"{c['floor']:.3f}"
        lines.append(f"{c['gate']:32s} {floor:>8s} {obs:>10s}  {c['status']}")
    lines.append(
        f"oracle: {report['oracle'].get('status')}"
        + (f" ({report['oracle']['reason']})" if report["oracle"].get("reason") else "")
    )
    return "\n".join(lines)


def load_frames_from_dir(out_dir: Path, seasons: Iterable[int]) -> dict[int, pl.DataFrame]:
    frames = {}
    for s in seasons:
        p = Path(out_dir) / f"{TAG}_{s}.parquet"
        if not p.is_file():
            raise SystemExit(f"gates: missing built asset {p}")
        frames[int(s)] = pl.read_parquet(p)
    return frames


def load_frames_from_release(seasons: Iterable[int]) -> dict[int, pl.DataFrame]:
    import requests

    frames = {}
    for s in seasons:
        r = requests.get(f"{RELEASE_BASE}/{TAG}_{s}.parquet", timeout=120)
        if r.status_code == 200:
            frames[int(s)] = pl.read_parquet(io.BytesIO(r.content))
    if not frames:
        raise SystemExit("gates: no release assets found for the requested seasons")
    return frames


def check_publish_floors(
    out_dir: Path,
    seasons: Iterable[int],
    *,
    oracle_dir: Optional[str] = None,
) -> dict:
    """Publish-blocking gate: evaluate the built seasons, record the report in the
    model card, and refuse (``SystemExit``) on any FAIL. SKIPPED never blocks and
    never counts as a pass — the printed table says which gates actually ran.
    """
    out_dir = Path(out_dir)
    seasons = sorted(int(s) for s in seasons)
    odir = oracle_dir or os.environ.get(ORACLE_DIR_ENV)
    report = gate_report(
        load_frames_from_dir(out_dir, seasons), oracle_dir=Path(odir) if odir else None
    )
    print("gates: publish floors (models/REGISTRY.md)\n" + format_report(report))
    card = out_dir / f"{TAG}_card.json"
    if card.is_file():
        payload = json.loads(card.read_text(encoding="utf-8"))
        payload["publish_gates"] = {"seasons_gated": seasons, **report}
        card.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    failed = [c for c in report["checks"] if c["status"] == "FAIL"]
    if failed:
        raise SystemExit(
            "gates: publish BLOCKED — "
            + "; ".join(
                f"{c['gate']} observed {c['observed']:.3f} < floor {c['floor']}" for c in failed
            )
            + " (never lower a floor to pass: debug the build)"
        )
    return report
