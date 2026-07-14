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
from typing import Any, Callable, Optional

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
        poss = compile_nba_season(
            season,
            lineup_source=lineup_source,
            cache_dir=cache_dir,
            proxy_provider=proxy_provider,
        )
        if poss.height == 0:
            print(f"impact: season={season} no possessions; skipped")
            prev_spm = None  # a gap season breaks the prior chain
            continue

        rapm = nba_rapm(poss)
        assert rapm.height > 0, f"impact: season={season} RAPM came back empty"

        # Box-log substrate (per-player + per-team leaguegamelog, one call each).
        logs = nba_box_logs(s_str, fetch=_leaguegamelog)
        bf = box_features(logs["player"], logs["team"])

        # SPM: within-season training on this season's RAPM target.
        coef = train_spm(bf, rapm.select("player_id", "o_rapm", "d_rapm"))
        spm = nba_spm(bf, coef)

        # BPM 2.0 off the same logs + listed positions.
        positions = nba_player_positions(s_str, fetch=_playerindex)
        bpm = nba_bpm(logs["player"], logs["team"], positions)

        # adj-RAPM: prior = previous season's SPM (empty dict on the first season).
        prior = AdjRapmModel.from_spm(prev_spm).prior if prev_spm is not None else {}
        adj = nba_adj_rapm(poss, prior)

        # WAR off the RAPM rating; pts_per_win calibrated from this season's
        # team logs (NBA has no ties, so plus_minus > 0 is a win).
        pts_per_win = calibrate_pts_per_win(_team_season(logs["team"]))
        war = nba_war(
            rapm.select("player_id", pl.col("rapm").alias("rating")),
            rapm.select(
                "player_id",
                (pl.col("off_poss") + pl.col("def_poss")).alias("poss"),
            ),
            replacement_level=replacement_level,
            pts_per_win=pts_per_win,
        )

        # DARKO panel: accumulate this season's RAPM ratings, forecast when the
        # panel spans >= 2 seasons.
        panel_frames.append(
            rapm.select(
                "player_id",
                pl.col("rapm").alias("rating"),
                (pl.col("off_poss") + pl.col("def_poss")).alias("weight"),
            ).with_columns(pl.lit(season, dtype=pl.Int64).alias("season"))
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
        if darko_season is not None:
            impact = _join_on_player(impact, darko_season, "darko")
        else:
            impact = impact.with_columns(
                [pl.lit(None, dtype=pl.Float64).alias(c) for c in _DARKO_COLS]
            )
        impact = impact.with_columns(pl.lit(season, dtype=pl.Int64).alias("season"))

        path = out_dir / f"nba_player_impact_{season}.parquet"
        impact.write_parquet(path)
        results.append({"season": season, "rows": impact.height, "path": str(path)})
        print(f"impact: season={season} rows={impact.height} -> {path}")

        prev_spm = spm

    if results:
        card_path = _write_model_card(
            out_dir,
            results,
            replacement_level=replacement_level,
            lineup_source=lineup_source,
        )
        print(f"impact: model card -> {card_path}")
    return results
