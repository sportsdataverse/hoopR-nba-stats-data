"""Build the consolidated per-season NBA player-impact table.

One ``nba_player_impact_{season}.parquet`` per season, one row per
player-season, joining the sdv-py NBA model-zoo outputs on ``player_id``:

* RAPM (``nba_rapm``) — the anchor population: every player with possession
  lineup data that season.
* adj-RAPM (``nba_adj_rapm``) — prior = the **previous season's SPM** frame
  (``AdjRapmModel.from_spm``), threaded earliest-to-latest; the first season
  of an invocation gets an empty prior.
* SPM (``train_spm`` + ``nba_spm``) — trained **within-season** (features and
  RAPM target from the same season) so a season's output never depends on
  which other seasons the invocation happened to include.
* BPM 2.0 (``nba_bpm``) — box logs + listed positions.
* WAR (``nba_war``) — ``pts_per_win`` calibrated per season from the team game
  logs (OLS wins ~ total margin); ``replacement_level`` defaults to ``-2.0``
  per 100 (the basketball-reference VORP convention) because the module
  intentionally ships no invented default.
* DARKO (``nba_darko``) — Kalman forecast off the multi-season RAPM panel
  accumulated **within this invocation**; seasons before the panel has two
  distinct seasons carry null ``darko_*`` columns.

Fidelity note for single-season runs (the nightly cron): pass a few trailing
seasons (e.g. ``--seasons 2021:2025``) — the per-game possession cache makes
prior seasons cheap, and they give adj-RAPM a real prior and DARKO a real
panel. Re-uploading trailing seasons is safe (``--clobber``).

Requires live stats.nba.com access (droplet + proxy host; cloud IPs hang).
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import polars as pl
from sportsdataverse.nba import (
    AdjRapmModel,
    box_features,
    calibrate_pts_per_win,
    compile_nba_season,
    nba_adj_rapm,
    nba_bpm,
    nba_box_logs,
    nba_darko,
    nba_player_ages,
    nba_player_positions,
    nba_spm,
    nba_war,
    train_spm,
)

# nba_rapm is NOT re-exported from the sportsdataverse.nba package (verified on
# main) — it lives in the nba_rapm submodule.
from sportsdataverse.nba.nba_rapm import nba_rapm
from sportsdataverse.nba.nba_stats import (
    nba_stats_leaguedashplayerbiostats,
    nba_stats_leaguegamelog,
    nba_stats_playerindex,
)

#: Zero-arg callable yielding a proxy URL (``RoundRobin.next`` matches this).
ProxyProvider = Callable[[], Optional[str]]

#: basketball-reference VORP replacement level, points per 100 possessions
#: relative to league average. ``nba_war`` requires an explicit value.
DEFAULT_REPLACEMENT_LEVEL = -2.0

_DARKO_COLS = ["darko_filtered_skill", "darko_projected_rating", "darko_projected_sd"]


def _season_str(year: int) -> str:
    """Season start year -> stats.nba.com season string (2023 -> ``"2023-24"``)."""
    return f"{year}-{(year + 1) % 100:02d}"


def _join_on_player(base: pl.DataFrame, right: pl.DataFrame, name: str) -> pl.DataFrame:
    """Left-join *right* onto *base* on ``player_id`` with the guard rails.

    Asserts join-key dtype agreement (everything in the zoo emits
    ``player_id: Int64``), key uniqueness on the right side, and that the join
    did not change the base height (a duplicate-key explosion or key-dtype
    mismatch would).
    """
    assert right.schema["player_id"] == pl.Int64, (
        f"{name}: player_id dtype {right.schema['player_id']} != Int64"
    )
    assert base.schema["player_id"] == right.schema["player_id"], (
        f"{name}: join-key dtype mismatch"
    )
    assert right["player_id"].n_unique() == right.height, (
        f"{name}: duplicate player_id rows"
    )
    joined = base.join(right, on="player_id", how="left")
    assert joined.height == base.height, (
        f"{name}: join changed height {base.height} -> {joined.height}"
    )
    return joined


def _team_season(team_logs: pl.DataFrame) -> pl.DataFrame:
    """Team game logs -> one row per team-season (``team_id, wins, total_margin``).

    NBA games have no ties, so ``plus_minus > 0`` is a win.
    """
    return team_logs.group_by("team_id").agg(
        (pl.col("plus_minus") > 0).sum().alias("wins"),
        pl.col("plus_minus").sum().alias("total_margin"),
    )


def _blend_by_poss(
    rs: pl.DataFrame,
    po: Optional[pl.DataFrame],
    value_cols: list[str],
    weight_col: str,
) -> pl.DataFrame:
    """Possession-weighted combination of a regular-season and playoff frame.

    The ONE forward-carrying rule: both the next season's adj-RAPM prior and the
    DARKO panel row use this. A playoff sample is ~15 games/team, so a straight
    "most recent estimate wins" carry would let a thin sample override a
    1230-game one -- adding playoffs would then DEGRADE every regular-season row.
    Weighting by possessions keeps the full RS sample behind the carried value
    while still letting playoff form move it.

    A player in only one frame keeps that frame's values (not null, not halved).

    Args:
        rs: Regular-season frame; one row per ``player_id``.
        po: Playoff frame, or None/empty -- either returns *rs* untouched.
        value_cols: Columns to weight-average.
        weight_col: Possession-count column; summed in the output.

    Returns:
        One row per ``player_id`` with blended *value_cols* and summed *weight_col*.
    """
    if po is None or po.height == 0:
        return rs

    joined = rs.join(po, on="player_id", how="full", coalesce=True, suffix="_po")
    w_rs = pl.col(weight_col).fill_null(0)
    w_po = pl.col(f"{weight_col}_po").fill_null(0)
    total = w_rs + w_po

    exprs = []
    for c in value_cols:
        v_rs, v_po = pl.col(c), pl.col(f"{c}_po")
        exprs.append(
            pl.when(total == 0)
            .then(v_rs.fill_null(v_po))
            .otherwise(
                (v_rs.fill_null(0) * w_rs + v_po.fill_null(0) * w_po) / total
            )
            .alias(c)
        )
    exprs.append(total.alias(weight_col))
    return joined.select("player_id", *exprs)


def _write_model_card(
    out_dir: Path, results: list[dict], *, replacement_level: float, lineup_source: str
) -> Path:
    from sportsdataverse.nba.nba_season_compile import PIPELINE_VERSION

    card = {
        "dataset": "nba_player_impact",
        "description": (
            "Consolidated per-season NBA player-impact table: RAPM, adj-RAPM, "
            "SPM, BPM 2.0, WAR, and DARKO forecasts joined on player_id. One "
            "parquet per season, one row per player-season. Base population = "
            "players with possession lineup data (RAPM-rated)."
        ),
        "source": "stats.nba.com (playbyplayv3 / gamerotation / boxscoretraditionalv3 / leaguegamelog / playerindex / leaguedashplayerbiostats)",
        "producer": "hoopR-nba-stats-data/python/nba_model_publish",
        "models": {
            "rapm": "sportsdataverse.nba.nba_rapm (single-season ridge)",
            "adj_rapm": "sportsdataverse.nba.nba_adj_rapm; prior = previous season's SPM (empty for the first season of an invocation)",
            "spm": "sportsdataverse.nba.train_spm + nba_spm, trained within-season on that season's box features + RAPM target",
            "bpm": "sportsdataverse.nba.nba_bpm (BPM 2.0, season granularity)",
            "war": (
                "sportsdataverse.nba.nba_war on the RAPM rating; pts_per_win "
                "calibrated per season from team game logs (OLS wins ~ total "
                f"margin); replacement_level = {replacement_level} per 100 "
                "(basketball-reference VORP convention)"
            ),
            "darko": (
                "sportsdataverse.nba.nba_darko on the within-invocation RAPM "
                "panel (rating=rapm, weight=off_poss+def_poss); darko_* columns "
                "are null until the panel spans >= 2 seasons"
            ),
        },
        "possession_pipeline_version": PIPELINE_VERSION,
        "lineup_source": lineup_source,
        "seasons": [{"season": r["season"], "rows": r["rows"]} for r in results],
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
    }
    path = out_dir / "nba_player_impact_card.json"
    path.write_text(json.dumps(card, indent=2))
    return path


def _proxied(
    wrapper: Callable[..., Any], provider: Optional[ProxyProvider]
) -> Callable[..., Any]:
    """Wrap an ``nba_stats_*`` callable so each call draws a fresh proxy from *provider*.

    ``nba_box_logs`` / ``nba_player_positions`` / ``nba_player_ages`` each take a
    ``fetch=`` seam documented as "an injectable ``nba_stats_*`` replacement" —
    so the proxied form is just the same wrapper with a rotating ``proxy_url``.
    Returns *wrapper* unchanged when there is no provider (local/residential runs).
    """
    if provider is None:
        return wrapper

    def _f(*args: Any, **kwargs: Any) -> Any:
        return wrapper(*args, proxy_url=provider(), **kwargs)

    return _f


def build_nba_player_impact(
    seasons: list[int],
    out_dir,
    *,
    lineup_source: str = "auto",
    cache_dir: Optional[str] = None,
    delay_s: float = 0.6,
    season_types: Sequence[str] = ("Regular Season", "Playoffs"),
    replacement_level: float = DEFAULT_REPLACEMENT_LEVEL,
    proxy_provider: Optional[ProxyProvider] = None,
) -> list[dict]:
    """Build per-season consolidated player-impact tables and write parquet.

    Seasons are processed earliest-to-latest so the adj-RAPM prior and the
    DARKO panel flow forward. Seasons whose possession compile comes back
    empty (not yet played / no data) are skipped with a notice.

    Args:
        seasons: Season start years (2023 = 2023-24). Sorted ascending
            internally.
        out_dir: Output directory (created if absent).
        lineup_source: Forwarded to ``compile_nba_season``.
        cache_dir: Possession per-game parquet cache directory (forwarded to
            ``compile_nba_season``; default resolves to ``$SDV_PY_NBA_CACHE_DIR``
            or ``~/.sdv_py_nba_cache/possessions``).
        delay_s: Sleep between live per-game fetches, seconds (forwarded to
            ``compile_nba_season``; only live fetches sleep, cached games don't).
            Throttles the shared stats.nba.com budget (~250 req/10min).
        season_types: Season types to build, in order. The "Regular Season"
            pass fits the SPM coefficients and pts_per_win; the "Playoffs"
            pass reuses them (a playoff sample is ~15 games/team -- re-fitting
            trains noise on noise) and takes the regular season's SPM as its
            adj-RAPM prior. Rows are tagged with a ``season_type`` column.
            "PlayIn" is not supported.
        replacement_level: WAR replacement level, points per 100 possessions.
        proxy_provider: Zero-arg callable returning a proxy URL (e.g.
            ``RoundRobin.next``). ``stats.nba.com`` *hangs* rather than errors on
            datacenter/cloud IPs, so an unattended host MUST supply one.
            It is threaded into **all four** network surfaces this builder
            touches — the possession compile (playbyplayv3 / gamerotation /
            boxscoretraditionalv3) AND leaguegamelog, playerindex, and
            leaguedashplayerbiostats. Proxying only the compile would leave the
            other three fetching from the host's real IP and hang the run.

    Returns:
        List of ``{"season": int, "rows": int, "path": str}`` dicts, one per
        season built, in season order.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    prev_spm: Optional[pl.DataFrame] = None
    panel_frames: list[pl.DataFrame] = []
    age_frames: list[pl.DataFrame] = []

    # Every stats.nba.com surface this builder touches must be proxied, not just
    # the possession compile -- an unproxied leaguegamelog/playerindex call hangs
    # the whole run on a datacenter host.
    _leaguegamelog = _proxied(nba_stats_leaguegamelog, proxy_provider)
    _playerindex = _proxied(nba_stats_playerindex, proxy_provider)
    _biostats = _proxied(nba_stats_leaguedashplayerbiostats, proxy_provider)

    for season in sorted(seasons):
        s_str = _season_str(season)
        frames: list[pl.DataFrame] = []
        rapm_rs: Optional[pl.DataFrame] = None
        spm_rs: Optional[pl.DataFrame] = None
        rapm_po: Optional[pl.DataFrame] = None
        spm_po: Optional[pl.DataFrame] = None
        coef = None
        pts_per_win = None
        # Season-type-independent -- lazily fetched once per season (guarded
        # below), NOT hoisted here: a gap season (RS empty) must pay ZERO
        # playerindex requests, and a both-types build must still fire the
        # identical request only once against the shared ~250 req/10min
        # stats.nba.com budget.
        positions: Optional[pl.DataFrame] = None

        for stype in season_types:
            poss = compile_nba_season(
                season,
                season_type=stype,
                lineup_source=lineup_source,
                cache_dir=cache_dir,
                delay_s=delay_s,
                proxy_provider=proxy_provider,
            )
            if poss.height == 0:
                if stype == "Regular Season":
                    # No RS pass means no fitted coef/pts_per_win -- falling
                    # through to the Playoffs pass would hit "playoff pass
                    # requires the regular-season coef" and abort the WHOLE
                    # multi-season run (this killed a real [2022, 2023-empty,
                    # 2024] backfill: 2024 never built, no model card). Skip
                    # this season entirely instead.
                    print(
                        f"impact: season={season} type={stype!r} REGULAR SEASON "
                        f"EMPTY -- skipping season {season} entirely (no coef/"
                        f"pts_per_win for a Playoffs pass); prior chain reset"
                    )
                    prev_spm = None  # a gap season breaks the prior chain
                    break
                # A season can legitimately have no playoffs (lockout, in-progress).
                # This is NOT the same as a network failure: the empty-in/empty-out
                # contract is exactly what made the unproxied-discovery bug exit 0
                # with no data, so say which case this is.
                print(f"impact: season={season} type={stype!r} no possessions; skipped")
                continue

            # Fetched once per season, on the first pass that actually has
            # possessions (normally the Regular Season pass) -- a gap season
            # breaks out above and never reaches this line, so it pays zero
            # playerindex requests.
            if positions is None:
                positions = nba_player_positions(s_str, fetch=_playerindex)

            rapm = nba_rapm(poss)
            assert rapm.height > 0, f"impact: season={season} {stype} RAPM came back empty"

            # Box-log substrate (per-player + per-team leaguegamelog, one call each).
            logs = nba_box_logs(s_str, season_type=stype, fetch=_leaguegamelog)
            bf = box_features(logs["player"], logs["team"])

            if stype == "Regular Season":
                # Fitted ONCE, on the regular season; the playoff pass reuses both.
                coef = train_spm(bf, rapm.select("player_id", "o_rapm", "d_rapm"))
                pts_per_win = calibrate_pts_per_win(_team_season(logs["team"]))
                prior = AdjRapmModel.from_spm(prev_spm).prior if prev_spm is not None else {}
            else:
                assert coef is not None, "playoff pass requires the regular-season coef"
                # Within the season, the playoff fit is anchored on the RS estimate --
                # that prior is what makes a ~15-game sample usable at all.
                prior = AdjRapmModel.from_spm(spm_rs).prior if spm_rs is not None else {}

            spm = nba_spm(bf, coef)

            # BPM 2.0 off the same logs + listed positions (fetched once above).
            bpm = nba_bpm(logs["player"], logs["team"], positions)

            # adj-RAPM: prior threaded in above (previous-season SPM for RS,
            # this season's RS SPM for PO).
            adj = nba_adj_rapm(poss, prior)

            # WAR off the RAPM rating; pts_per_win calibrated once, from the
            # regular season's team logs (NBA has no ties, so plus_minus > 0 is
            # a win), and reused for the playoff pass.
            war = nba_war(
                rapm.select("player_id", pl.col("rapm").alias("rating")),
                rapm.select(
                    "player_id",
                    (pl.col("off_poss") + pl.col("def_poss")).alias("poss"),
                ),
                replacement_level=replacement_level,
                pts_per_win=pts_per_win,
            )

            if stype == "Regular Season":
                rapm_rs, spm_rs = rapm, spm
            else:
                rapm_po, spm_po = rapm, spm

            impact = rapm
            impact = _join_on_player(
                impact,
                adj.select("player_id", "o_adj_rapm", "d_adj_rapm", "adj_rapm"),
                "adj_rapm",
            )
            impact = _join_on_player(
                impact, spm.select("player_id", "ospm", "dspm", "spm", "min", "gp"), "spm"
            )
            impact = _join_on_player(
                impact, bpm.select("player_id", "obpm", "dbpm", "bpm"), "bpm"
            )
            impact = _join_on_player(impact, war, "war")
            impact = impact.with_columns(
                pl.lit(season, dtype=pl.Int64).alias("season"),
                pl.lit(stype, dtype=pl.Utf8).alias("season_type"),
            )
            frames.append(impact)

        if not frames:
            continue

        # --- DARKO panel: ONE row per player-season ---------------------------
        # DARKO is a per-season Kalman filter + aging curve projecting NEXT
        # season. Inserting a playoff time step would apply a season of aging
        # twice and mis-scale the per-season process variance, so playoff form
        # enters as a possession-weighted blend instead of a second step.
        panel_rs = rapm_rs.select(
            "player_id",
            pl.col("rapm").alias("rating"),
            (pl.col("off_poss") + pl.col("def_poss")).alias("weight"),
        )
        panel_po = (
            rapm_po.select(
                "player_id",
                pl.col("rapm").alias("rating"),
                (pl.col("off_poss") + pl.col("def_poss")).alias("weight"),
            )
            if rapm_po is not None
            else None
        )
        panel_frames.append(
            _blend_by_poss(panel_rs, panel_po, ["rating"], "weight").with_columns(
                pl.lit(season, dtype=pl.Int64).alias("season")
            )
        )
        age_frames.append(
            nba_player_ages(s_str, fetch=_biostats).with_columns(
                pl.lit(season, dtype=pl.Int64).alias("season")
            )
        )
        panel = pl.concat(panel_frames)
        if panel["season"].n_unique() >= 2:
            darko = nba_darko(panel, pl.concat(age_frames))
            darko_season = darko.filter(pl.col("last_season") == season).select(
                "player_id",
                pl.col("filtered_skill").alias("darko_filtered_skill"),
                pl.col("projected_rating").alias("darko_projected_rating"),
                pl.col("projected_sd").alias("darko_projected_sd"),
            )
        else:
            darko_season = None

        # DARKO projects NEXT season, which is not a playoff-specific quantity:
        # both season_type rows carry the same projection.
        out_frames = []
        for f in frames:
            if darko_season is not None:
                f = _join_on_player(f, darko_season, "darko")
            else:
                f = f.with_columns(
                    [pl.lit(None, dtype=pl.Float64).alias(c) for c in _DARKO_COLS]
                )
            out_frames.append(f)
        impact = pl.concat(out_frames, how="vertical")

        path = out_dir / f"nba_player_impact_{season}.parquet"
        impact.write_parquet(path)
        results.append({"season": season, "rows": impact.height, "path": str(path)})
        print(
            f"impact: season={season} rows={impact.height} "
            f"types={impact['season_type'].unique().to_list()} -> {path}"
        )

        # --- forward carry ---------------------------------------------------
        # The next season's adj-RAPM prior is the possession-weighted RS+PO
        # blend, NOT the playoff estimate: a ~15-game sample must not override a
        # 1230-game one as the prior for the following regular season.
        if spm_po is not None:
            prev_spm = _blend_by_poss(
                spm_rs, spm_po, ["ospm", "dspm", "spm"], "min"
            )
        else:
            prev_spm = spm_rs

    if results:
        card_path = _write_model_card(
            out_dir,
            results,
            replacement_level=replacement_level,
            lineup_source=lineup_source,
        )
        print(f"impact: model card -> {card_path}")
    return results
