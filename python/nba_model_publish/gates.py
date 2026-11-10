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
    # observed min 428 (2003) over complete seasons; max 605 (2022). Lowered from 400 on
    # 2026-10-26 (owner): the nightly publishes the CURRENT season, which had 397 RS
    # player rows six days in, and a full-season floor blocked it.
    "rs_rows_min": 350,
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
            pair = rs.select("player_id", "rapm", "boban_projected_rating").join(
                _rs(nxt).select("player_id", pl.col("rapm").alias("next_rapm")),
                on="player_id",
                how="inner",
            )
            row["r_rapm_yoy"] = _pearson(pair, "rapm", "next_rapm")
            row["r_darko_fwd"] = _pearson(pair, "boban_projected_rating", "next_rapm")
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
            # Scale ratios against the SAME oracle rows we already correlate on.
            # SCALE_BANDS below are calibrated from our own published history, so
            # they can only catch a CHANGE -- never a miscalibration that was
            # already there when the band was set. These ratios are the missing
            # EXTERNAL anchor: 1.0 means we match EPM's dispersion on the joined
            # players. Measured 2026-09-03 on the published 2026 tag,
            # adj_rapm/epm came out ~2.1x while rapm/epm was ~0.96, and
            # o_adj_rapm peaked at +22.0 where no oracle rating exceeds +6.4.
            sd_epm = _sd(m, "epm")
            res["epm"][str(season)] = {
                "n": m.height,
                "r_rapm": _pearson(m, "rapm", "epm"),
                "r_adj_rapm": _pearson(m, "adj_rapm", "epm"),
                "r_minutes": _pearson(m, "min", "epm"),
                "sd_ratio_rapm": _ratio(_sd(m, "rapm"), sd_epm),
                "sd_ratio_adj_rapm": _ratio(_sd(m, "adj_rapm"), sd_epm),
            }
    return res


def _sd(frame: pl.DataFrame, col: str) -> Optional[float]:
    """Sample SD of *col*, or None when it cannot be measured."""
    if col not in frame.columns or frame.height < 2:
        return None
    # drop_nans() as well as drop_nulls(): polars keeps IEEE NaN through
    # drop_nulls(), one NaN makes .std() return nan, and json.dumps writes a
    # non-standard `NaN` token that strict model-card consumers reject.
    v = frame[col].drop_nulls().drop_nans()
    if v.len() < 2:
        return None
    sd = float(v.std())
    return None if math.isnan(sd) or math.isinf(sd) else sd


def _ratio(num: Optional[float], den: Optional[float]) -> Optional[float]:
    """num / den, or None when either side is missing or the denominator is ~0."""
    if num is None or den is None or abs(den) < 1e-9:
        return None
    return float(num / den)


def _min_of(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return min(vals) if vals else None


#: Publish-blocking SCALE bands. Every gate in FLOORS above is a CORRELATION or a
#: row count, and a correlation is invariant to an affine rescale -- a season whose
#: ratings all came out 10x too large passes every one of them. That is exactly how
#: mis-scaled "xwOBA" of .44-.73 shipped on 2026-09-01 (baseballr-data 75d29ddbc5).
#:
#: Two-sided bands on the qualified league LEVEL, set strictly outside the values
#: observed on the published release (seasons 1997-2026, measured 2026-09-02 with
#: off_poss >= 500); the comment records the observation that set each one.
#: Never widen a band to make a publish pass -- debug the build.
#:
#: KNOWN LIMIT of these bands: they are set from OUR OWN published values, so they
#: can only catch a CHANGE -- never a miscalibration already present when a band is
#: drawn. `sd_adj_rapm` was the worked example: (3.0, 8.0) was drawn around "observed
#: 4.47 - 6.20" while the external oracles read a player-rating SD near 2.3 (EPM
#: 2.281, DARKO 1.760) on the same 2026 rows, i.e. adj_rapm ~2.1x too wide.
#:
#: Resolved 2026-11-09. sportsdataverse-py #1137 gave the adj-RAPM ridge an
#: unpenalized intercept (o/d had absorbed the league's points per possession, means
#: ~+11 / -11) and #1150 fits it at one penalty per league with a 2x SPM prior. On
#: 8a5f511b, 1997-2026 read sd_adj_rapm 1.64 (1999) - 2.06 (2016), sd_adj_rapm /
#: sd_rapm 0.94 - 1.16 (no collapsed season); 2026 reads 1.99 = 0.87x EPM, 1.13x
#: DARKO. sd_adj_rapm is re-derived from that history by the 2026-09-02 method
#: (round values strictly outside the observed range, floor ~0.6x, ceiling ~1.5x).
#: Keep the oracle_checks() sd_ratio_* metrics as the external check on it.
SCALE_QUALIFY_POSS = 500
#: Season-maturity minimum (owner, 2026-11-08). A season with fewer qualified players
#: (off_poss >= SCALE_QUALIFY_POSS, every season type) than this is IMMATURE: its scale
#: bands and its per-season correlation floors are SKIPPED, not evaluated, because an
#: in-progress season's ratings are noisy against bands and floors drawn from complete
#: ones. Observed: complete seasons 1997-2026 carry 366 (1999 lockout) - 507 (2026);
#: 2027 carried 3 on 2026-11-03, and on 2026-11-07 failed sd_adj_rapm 9.26 and
#: r_rapm_adj 0.735 at well under this count. This is a sample minimum, not a widened
#: band or a lowered floor -- a mature season still has to pass every one of them.
MIN_QUALIFIED_PLAYERS = 250
SCALE_BANDS: dict[str, tuple[float, float]] = {
    "mean_rapm": (-1.0, 1.0),  # observed |mean| <= 0.19
    "sd_rapm": (0.5, 3.5),  # observed 0.99 - 2.27
    "mean_adj_rapm": (-3.0, 3.0),  # observed |mean| <= 1.00
    "sd_adj_rapm": (1.0, 3.0),  # observed 1.64 - 2.06 (2026-11-09, #1150; see above)
}


def scale_checks(frames: dict[int, pl.DataFrame]) -> list[dict]:
    """Evaluate every season's qualified level against SCALE_BANDS.

    A season with too few qualified players to measure is SKIPPED, which is not
    PASS -- the printed table says which seasons actually ran.
    """
    out: list[dict] = []
    for season in sorted(frames):
        frame = frames[season]
        missing = [c for c in ("off_poss", "rapm", "adj_rapm") if c not in frame.columns]
        if missing:
            # cannot measure a level without these -- SKIPPED, never PASS
            out.append(
                {
                    "season": season,
                    "gate": "scale",
                    "status": "SKIPPED",
                    "reason": f"frame has no {', '.join(missing)}",
                }
            )
            continue
        qualified = frame.filter(pl.col("off_poss") >= SCALE_QUALIFY_POSS)
        if qualified.height < MIN_QUALIFIED_PLAYERS:
            out.append(
                {
                    "season": season,
                    "gate": "scale",
                    "status": "SKIPPED",
                    "reason": f"season immature: {qualified.height} qualified players "
                    f"< {MIN_QUALIFIED_PLAYERS}",
                }
            )
            continue
        stats = {
            "mean_rapm": qualified["rapm"].mean(),
            "sd_rapm": qualified["rapm"].std(),
            "mean_adj_rapm": qualified["adj_rapm"].mean(),
            "sd_adj_rapm": qualified["adj_rapm"].std(),
        }
        for name, (lo, hi) in SCALE_BANDS.items():
            observed = stats[name]
            if observed is None:
                out.append(
                    {
                        "season": season,
                        "gate": name,
                        "status": "SKIPPED",
                        "reason": "not computable",
                    }
                )
                continue
            observed = float(observed)
            out.append(
                {
                    "season": season,
                    "gate": name,
                    "observed": observed,
                    "band": [lo, hi],
                    "status": "PASS" if lo <= observed <= hi else "FAIL",
                }
            )
    return out


def gate_report(frames: dict[int, pl.DataFrame], *, oracle_dir: Optional[Path] = None) -> dict:
    """Compute every diagnostic and evaluate it against ``FLOORS``.

    Pure computation: never raises on a failing gate (the caller decides), and
    a metric that cannot be computed from the frames given (a single season has
    no forward pair) is SKIPPED, which is not PASS.
    """
    seasons = internal_metrics(frames)
    immature = immature_seasons(frames)
    for s, row in seasons.items():
        row["immature"] = int(s) in immature
    per = seasons.values()
    # An immature season's correlations are not gated (MIN_QUALIFIED_PLAYERS); a forward
    # pair is excluded when either end is immature. rs_rows still applies to every season.
    own = [r for s, r in seasons.items() if int(s) not in immature]
    fwd_rows = [r for s, r in seasons.items() if not {int(s), int(s) + 1} & immature]
    summary: dict[str, Optional[float]] = {
        "rs_rows_min": _min_of(r["rs_rows"] for r in per),
        "r_rapm_adj_min": _min_of(r["r_rapm_adj"] for r in own),
        "r_spm_rapm_min": _min_of(r["r_spm_rapm"] for r in own),
        "r_rapm_yoy_min": _min_of(r["r_rapm_yoy"] for r in fwd_rows),
        "r_darko_fwd_min": _min_of(r["r_darko_fwd"] for r in fwd_rows),
    }
    fwd = [
        (r["r_darko_fwd"], r["n_fwd"])
        for r in fwd_rows
        if r["r_darko_fwd"] is not None and r["n_fwd"]
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
    return {
        "seasons": seasons,
        "summary": summary,
        "oracle": oracle,
        "checks": checks,
        "immature_seasons": sorted(immature),
    }


def immature_seasons(frames: dict[int, pl.DataFrame]) -> set[int]:
    """Seasons with fewer than MIN_QUALIFIED_PLAYERS qualified players.

    A frame without ``off_poss``, or with no non-null value in it, cannot be measured
    and is treated as mature, so a build that drops or blanks the column is still
    gated rather than waved through. Counts qualifying ROWS (every season type), the
    same rows the scale bands measure and the count MIN_QUALIFIED_PLAYERS was drawn from.
    """
    return {
        s
        for s, f in frames.items()
        if "off_poss" in f.columns
        and f["off_poss"].null_count() < f.height
        and f.filter(pl.col("off_poss") >= SCALE_QUALIFY_POSS).height < MIN_QUALIFIED_PLAYERS
    }


def format_report(report: dict) -> str:
    lines = [f"{'gate':32s} {'floor':>8s} {'observed':>10s}  status"]
    for c in report["checks"]:
        obs = "—" if c["observed"] is None else f"{c['observed']:.3f}"
        floor = "—" if c["floor"] is None else f"{c['floor']:.3f}"
        lines.append(f"{c['gate']:32s} {floor:>8s} {obs:>10s}  {c['status']}")
    if report.get("immature_seasons"):
        lines.append(
            f"immature (< {MIN_QUALIFIED_PLAYERS} qualified players; correlation floors "
            f"SKIPPED): {', '.join(map(str, report['immature_seasons']))}"
        )
    lines.append(
        f"oracle: {report['oracle'].get('status')}"
        + (f" ({report['oracle']['reason']})" if report["oracle"].get("reason") else "")
    )
    return "\n".join(lines)


#: BB-D11 renamed the published ``darko_*`` columns to ``boban_*``; a season published before the
#: rename still carries the old names until it is republished.
_BOBAN_RENAMES = {
    "darko_filtered_skill": "boban_filtered_skill",
    "darko_projected_rating": "boban_projected_rating",
    "darko_projected_sd": "boban_projected_sd",
}


def _boban_names(frame: pl.DataFrame) -> pl.DataFrame:
    """A published frame with the ``boban_*`` names, whichever the season was published with."""
    return frame.rename(
        {o: n for o, n in _BOBAN_RENAMES.items() if o in frame.columns and n not in frame.columns}
    )


def load_frames_from_dir(out_dir: Path, seasons: Iterable[int]) -> dict[int, pl.DataFrame]:
    seasons = list(seasons)
    if not seasons:
        # Returning {} here made check_publish_floors() emit only SKIPPED rows and
        # exit 0 -- every publish gate bypassed, looking exactly like a pass.
        raise SystemExit("gates: no seasons requested; refusing to report an all-SKIPPED pass")
    frames = {}
    for s in seasons:
        p = Path(out_dir) / f"{TAG}_{s}.parquet"
        if not p.is_file():
            raise SystemExit(f"gates: missing built asset {p}")
        frames[int(s)] = _boban_names(pl.read_parquet(p))
    return frames


def load_frames_from_release(seasons: Iterable[int]) -> dict[int, pl.DataFrame]:
    import requests

    frames = {}
    unavailable = {}
    for s in seasons:
        r = requests.get(f"{RELEASE_BASE}/{TAG}_{s}.parquet", timeout=120)
        if r.status_code == 200:
            frames[int(s)] = _boban_names(pl.read_parquet(io.BytesIO(r.content)))
        else:
            unavailable[int(s)] = r.status_code
    # Symmetric with load_frames_from_dir, which raises on a missing built asset. Dropping
    # the season instead would evaluate a SHORTER season set than the caller asked for, and
    # a forward gate that never ran reports SKIPPED -- which the CLI does not treat as a
    # FAIL, so an absent release asset would exit 0. A requested season that is not there
    # is an error, not an empty answer.
    if unavailable:
        raise SystemExit(
            "gates: release assets unavailable for requested seasons "
            + ", ".join(f"{s} (HTTP {c})" for s, c in sorted(unavailable.items()))
            + " -- refusing to gate a partial season set (a SKIPPED gate is not a pass)"
        )
    if not frames:
        raise SystemExit("gates: no seasons requested")
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
    scale = scale_checks(load_frames_from_dir(out_dir, seasons))
    report["scale"] = scale
    scale_failed = [c for c in scale if c["status"] == "FAIL"]
    scale_ran = [c for c in scale if c["status"] != "SKIPPED"]
    print(
        f"gates: scale bands (qualified off_poss >= {SCALE_QUALIFY_POSS}) — "
        f"{len(scale_ran) - len(scale_failed)}/{len(scale_ran)} pass"
    )
    print("gates: publish floors (models/REGISTRY.md)\n" + format_report(report))
    card = out_dir / f"{TAG}_card.json"
    if not card.is_file():
        # builders.py writes this unconditionally at the end of a build, and gates
        # run after one -- so an absent card means the build did not finish. The
        # publish-gate contract is that the card RECORDS the gates; skipping the
        # write silently would let a publish succeed with no gate record at all.
        raise SystemExit(f"gates: model card missing at {card}; the build did not complete")
    payload = json.loads(card.read_text(encoding="utf-8"))
    payload["publish_gates"] = {"seasons_gated": seasons, **report}
    card.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if scale_failed:
        raise SystemExit(
            "gates: publish SCALE BLOCKED — "
            + "; ".join(
                f"{c['season']} {c['gate']} observed {c['observed']:.4f} "
                f"outside band {c['band'][0]}..{c['band'][1]}"
                for c in scale_failed
            )
            + " (a correlation gate cannot see a rescale; never widen a band to pass)"
        )
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
