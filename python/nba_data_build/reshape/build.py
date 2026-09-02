"""Reshape raw-store captures into the published season frames.

Pure functions over payloads already on disk — no network, so a season compiles
from a fixture tree and every builder is testable offline.

Season-level datasets are one payload per season, optionally spread over parameter
variants (measure type x season type x per mode) which are bound into a single
frame with the varying parameters carried as columns. Game-level datasets are one
payload per game, bound per season.

Ported from the WNBA reshaper (``wehoop-wnba-stats-data``): the v3 payload nesting
is identical across leagues, so the extractors are unchanged. The only adaptation is
that reads route through :mod:`nba_data_build.reshape.raw`, which encodes NBA's
start↔end season split — no season/dir logic lives here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import polars as pl

from . import raw
from .datasets import Dataset

#: Split a word boundary, then a lower/digit-to-upper boundary. Two passes rather
#: than one lookahead so trailing acronyms survive: a naive split-before-capital
#: turns ``LeagueID`` into ``league_i_d``, and these are join keys -- a mangled id
#: column name breaks joins downstream instead of erroring here.
_WORD_THEN_CAP = re.compile(r"(.)([A-Z][a-z]+)")
_LOWER_THEN_CAP = re.compile(r"([a-z0-9])([A-Z])")


def snake(name: str) -> str:
    """``TEAM_ID`` / ``teamId`` / ``LeagueID`` -> ``team_id`` / ``league_id``.

    stats.com mixes SHOUTING_SNAKE (v2 resultSets) with camelCase (v3) and embeds
    acronyms in both, while the published datasets are snake_case throughout.
    """
    if name.isupper():
        return name.lower()
    out = _WORD_THEN_CAP.sub(r"\1_\2", name)
    out = _LOWER_THEN_CAP.sub(r"\1_\2", out)
    return out.lower().replace("__", "_")


def frame_from_result_set(
    headers: list[str], rows: list[list[Any]], extra: dict[str, Any] | None = None
) -> pl.DataFrame:
    """Build a frame from a resultSet, snake-casing columns.

    ``strict=False`` because stats.com occasionally flips a column's type between
    rows (an id arriving as int in one row and str in another); erroring there
    would abandon a whole season over one cell.
    """
    if not headers:
        return pl.DataFrame()
    cols = [snake(h) for h in headers]
    df = pl.DataFrame(
        {c: [r[i] if i < len(r) else None for r in rows] for i, c in enumerate(cols)},
        strict=False,
    )
    for key, value in (extra or {}).items():
        df = df.with_columns(pl.lit(value).alias(key))
    return df


def _variant_columns(variant: str | None) -> dict[str, str]:
    """Carry a capture's varying parameters into the frame as columns.

    Variant slugs are ``{season_type}_{measure_type}_{per_mode}`` (whichever axes an
    endpoint supports). Binding several variants without these would silently stack
    rows that mean different things -- Base next to Advanced with no way to tell.
    """
    if not variant:
        return {}
    parts = variant.split("_")
    names = ("season_type", "measure_type", "per_mode")
    return {n: p for n, p in zip(names, parts)}


def build_season_dataset(root: str | Path, dataset: Dataset, season: int) -> pl.DataFrame:
    """One season-level dataset, binding every captured parameter variant."""
    if dataset.endpoint is None:
        raise ValueError(f"{dataset.key} is derived; build it with its own builder")

    frames: list[pl.DataFrame] = []
    base = Path(root) / dataset.endpoint / str(raw.store_dir(dataset.endpoint, season))

    # Unparameterized capture lives at {endpoint}/{season}.json
    single = raw.read_season(root, dataset.endpoint, season)
    variants: list[tuple[str | None, Any]] = []
    if single is not None:
        variants.append((None, single))
    elif raw._is_url(root):
        # Variant names are a combinatorial sweep slug
        # ({season_type}_{measure}_{per_mode}, ...) and plain HTTP cannot list a
        # directory, so they cannot be discovered from a URL root. Silently
        # returning an empty frame here would publish a dataset that merely LOOKS
        # like the season had no data -- refuse instead, and point at the local
        # root that does work.
        raise ValueError(
            f"{dataset.key}: season {season} is variant-backed ({dataset.endpoint} has no "
            f"bare {season}.json), and its variants cannot be enumerated over HTTP. "
            "Use a local raw-store root -- scripts/hydrate_raw_store.sh materialises one "
            "from the published season bundles -- or pass --root to a checkout."
        )
    elif base.is_dir():
        for path in sorted(base.glob("*.json")):
            payload = raw.read_season(root, dataset.endpoint, season, path.stem)
            if payload is not None:
                variants.append((path.stem, payload))

    for variant, payload in variants:
        headers, rows = raw.result_set(payload, dataset.result_set)
        if not headers:
            continue
        extra = {"season": season, **_variant_columns(variant)}
        frames.append(frame_from_result_set(headers, rows, extra))

    if not frames:
        return pl.DataFrame()
    return frames[0] if len(frames) == 1 else pl.concat(frames, how="diagonal_relaxed")


def build_game_dataset(
    root: str | Path, dataset: Dataset, season: int, game_ids: list[str] | None = None
) -> pl.DataFrame:
    """One game-level dataset, bound across a season's captured games.

    Games with no capture are skipped rather than failing the season: a sweep is
    always partially complete, and a missing game should cost that game only.
    """
    if dataset.endpoint is None:
        raise ValueError(f"{dataset.key} is derived; build it with its own builder")

    if game_ids is None:
        game_ids = raw.season_game_ids(root, season) or raw.available_games(
            root, dataset.endpoint, season
        )

    frames: list[pl.DataFrame] = []
    for gid, payload in raw.iter_game_payloads(root, dataset.endpoint, game_ids):
        headers, rows = raw.result_set(payload, dataset.result_set)
        if not headers:
            continue
        frames.append(frame_from_result_set(headers, rows, {"season": season, "game_id": gid}))

    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def build(root: str | Path, dataset: Dataset, season: int) -> pl.DataFrame:
    """Dispatch to the season- or game-level builder for ``dataset``."""
    if dataset.level == "game":
        return build_game_dataset(root, dataset, season)
    return build_season_dataset(root, dataset, season)


# -- play-by-play + shots ------------------------------------------------------
#
# playbyplayv3 does not use the resultSets envelope: its rows live under
# game.actions as dicts, so it needs its own extractor rather than result_set().


def pbp_rows(payload: Any) -> list[dict[str, Any]]:
    """Action rows from one captured ``playbyplayv3`` payload."""
    if not isinstance(payload, dict):
        return []
    return [a for a in (payload.get("game") or {}).get("actions") or [] if isinstance(a, dict)]


def build_pbp(root: str | Path, season: int, game_ids: list[str] | None = None) -> pl.DataFrame:
    """Season play-by-play, bound across every captured game.

    Columns are snake-cased from the v3 camelCase field names. Rows are kept in
    capture order within a game and games in id order, so the frame is stable
    across rebuilds.
    """
    if game_ids is None:
        game_ids = raw.season_game_ids(root, season) or raw.available_games(
            root, "playbyplayv3", season
        )
    frames: list[pl.DataFrame] = []
    for gid, payload in raw.iter_game_payloads(root, "playbyplayv3", game_ids):
        rows = pbp_rows(payload)
        if not rows:
            continue
        df = pl.DataFrame(rows, infer_schema_length=None, strict=False)
        df = df.rename({c: snake(c) for c in df.columns})
        frames.append(df.with_columns(game_id=pl.lit(gid), season=pl.lit(season)))
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


#: Field-goal actions carry shot geometry; everything else in pbp does not.
#: Verified against the real NBA v3 store: playbyplayv3 actions expose the same
#: fields the WNBA reshaper filters on (isFieldGoal + shotResult/shotValue/
#: shotDistance/xLegacy/yLegacy), so this column set ports unchanged.
_SHOT_COLUMNS = (
    "game_id",
    "season",
    "period",
    "clock",
    "team_id",
    "team_tricode",
    "person_id",
    "player_name",
    "action_type",
    "sub_type",
    "shot_result",
    "shot_value",
    "shot_distance",
    "x_legacy",
    "y_legacy",
    "description",
    "score_home",
    "score_away",
)


def build_shots(pbp: pl.DataFrame) -> pl.DataFrame:
    """Shot attempts derived from play-by-play.

    Derived rather than fetched: every field the shots dataset needs is already in
    the pbp capture, so this costs no request and cannot drift from the pbp it is
    built from. Selects only the shot-relevant columns, keeping whichever are
    present -- the v3 field set varies across seasons.
    """
    if pbp.is_empty() or "is_field_goal" not in pbp.columns:
        return pl.DataFrame()
    shots = pbp.filter(pl.col("is_field_goal") == 1)
    keep = [c for c in _SHOT_COLUMNS if c in shots.columns]
    return shots.select(keep) if keep else shots


# -- traditional boxscores -----------------------------------------------------
#
# boxscoretraditionalv3 nests: boxScoreTraditional.{homeTeam,awayTeam} each carry
# a players[] list whose rows hold their counting stats in a `statistics` object.
# Flattening lifts those onto the row so the published frame is one row per
# player-game rather than a struct column no R consumer could read.


def _flatten_stats(row: dict[str, Any]) -> dict[str, Any]:
    """Lift a nested ``statistics`` object onto its parent row."""
    out = {k: v for k, v in row.items() if k != "statistics"}
    out.update(row.get("statistics") or {})
    return out


def boxscore_rows(payload: Any, *, team_level: bool) -> list[dict[str, Any]]:
    """Player- or team-level rows from one ``boxscoretraditionalv3`` payload."""
    if not isinstance(payload, dict):
        return []
    box = payload.get("boxScoreTraditional") or {}
    rows: list[dict[str, Any]] = []
    for side in ("homeTeam", "awayTeam"):
        team = box.get(side) or {}
        if not isinstance(team, dict):
            continue
        common = {
            "team_id": team.get("teamId"),
            # teamName alone is the nickname ("Pacers"), so without teamCity a
            # consumer cannot render or match on the full club name; the payload
            # carries both and dropping the city loses information for free.
            "team_city": team.get("teamCity"),
            "team_name": team.get("teamName"),
            "team_tricode": team.get("teamTricode"),
            "team_slug": team.get("teamSlug"),
            "side": "home" if side == "homeTeam" else "away",
        }
        if team_level:
            rows.append(
                {
                    **common,
                    **_flatten_stats({"statistics": team.get("statistics") or {}}),
                }
            )
        else:
            for player in team.get("players") or []:
                if isinstance(player, dict):
                    rows.append({**common, **_flatten_stats(player)})
    return rows


def build_boxscores(
    root: str | Path,
    season: int,
    *,
    team_level: bool,
    game_ids: list[str] | None = None,
) -> pl.DataFrame:
    """Season traditional boxscores, player- or team-level, bound across games."""
    if game_ids is None:
        game_ids = raw.season_game_ids(root, season) or raw.available_games(
            root, "boxscoretraditionalv3", season
        )
    frames: list[pl.DataFrame] = []
    for gid, payload in raw.iter_game_payloads(root, "boxscoretraditionalv3", game_ids):
        rows = boxscore_rows(payload, team_level=team_level)
        if not rows:
            continue
        df = pl.DataFrame(rows, infer_schema_length=None, strict=False)
        df = df.rename({c: snake(c) for c in df.columns})
        frames.append(df.with_columns(game_id=pl.lit(gid), season=pl.lit(season)))
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


# -- per-game matchups ---------------------------------------------------------
#
# boxscorematchupsv3 nests one level deeper than the traditional boxscore:
# boxScoreMatchups.{homeTeam,awayTeam}.players[] is that team's list of players,
# and each of those carries a matchups[] list -- one entry per opponent they
# shared the floor against -- with the pair's counting stats in a `statistics`
# object. Flattening gives one row per (game, offensive player, defender).
#
# WHICH SIDE IS WHICH IS NOT GUESSWORK, and it is not what nba_api's parser says:
# that parser names its loop variables `_def_pl` for the OUTER player and
# `_off_pl` for the nested one, while its own header builder suffixes the outer
# with "Off" and the nested with "Def" -- the two disagree inside one file, so
# neither can be cited. Measured instead, on the committed 0022300001 fixture:
# summing an outer player's matchup `playerPoints` reproduces that player's OWN
# points in boxscoretraditionalv3 (Mitchell 38 = 38, Allen 10 = 10, Mathurin
# 5 = 5), which holds only if the OUTER player is the one scoring. So outer =
# offense, nested = defender, matching the OFF_PLAYER_ID / DEF_PLAYER_ID columns
# the season-level `leagueseasonmatchups` endpoint publishes.
# tests/test_reshape_matchups.py::test_outer_player_is_the_offensive_player is
# that measurement, kept runnable -- getting this backwards would invert every
# defensive metric built on the dataset while looking perfectly well-formed.

#: The pair's own totals are not exact: points are credited per partial
#: possession, so a player's summed matchup points can exceed or fall short of
#: their game total (Turner 33 vs 27, Toppin 4 vs 6 in the same fixture). Only
#: the players whose scoring happened entirely against tracked defenders match
#: exactly, which is why the orientation test asserts on those and not on a
#: whole-team sum.


def matchup_rows(payload: Any) -> list[dict[str, Any]]:
    """One row per (offensive player, defender) pair from a ``boxscorematchupsv3`` payload."""
    if not isinstance(payload, dict):
        return []
    box = payload.get("boxScoreMatchups") or {}
    if not isinstance(box, dict):
        return []
    # The defending team is the other side; take it from the envelope's own ids
    # rather than the nested team object, which is 0 in uncovered captures.
    opponent_id = {
        "homeTeam": box.get("awayTeamId"),
        "awayTeam": box.get("homeTeamId"),
    }
    rows: list[dict[str, Any]] = []
    for side in ("homeTeam", "awayTeam"):
        team = box.get(side) or {}
        if not isinstance(team, dict):
            continue
        common = {
            "off_team_id": team.get("teamId"),
            "off_team_city": team.get("teamCity"),
            "off_team_name": team.get("teamName"),
            "off_team_tricode": team.get("teamTricode"),
            "off_team_slug": team.get("teamSlug"),
            "def_team_id": opponent_id[side],
            "side": "home" if side == "homeTeam" else "away",
        }
        for off in team.get("players") or []:
            if not isinstance(off, dict):
                continue
            off_cols = {f"off_{k}": v for k, v in off.items() if k != "matchups"}
            for defender in off.get("matchups") or []:
                if not isinstance(defender, dict):
                    continue
                def_cols = {f"def_{k}": v for k, v in defender.items() if k != "statistics"}
                stats = defender.get("statistics") or {}
                if not isinstance(stats, dict):
                    # A truthy non-mapping ("statistics": "invalid") would raise
                    # TypeError on the unpack below and abort the whole season
                    # for one bad capture -- the trade read_result_sets already
                    # makes. Skipped rather than emitted stats-less: a pair whose
                    # entire counting block is null reads as a real zero, which
                    # is worse than an absent pair. Silent, like the four sibling
                    # guards above -- this module is deliberately logger-free
                    # ("pure functions over payloads already on disk").
                    continue
                rows.append({**common, **off_cols, **def_cols, **stats})
    return rows


def build_matchups(
    root: str | Path, season: int, game_ids: list[str] | None = None
) -> pl.DataFrame:
    """Season player-vs-player matchups, bound across every captured game.

    Games whose payload carries empty ``players`` lists contribute no rows rather
    than a schema-only stripe: NBA tracked matchups for only 21 of the 1,414
    games in 2016-17 and for none at all before that, and the raw store holds a
    well-formed empty envelope for each of those.
    """
    if game_ids is None:
        game_ids = raw.season_game_ids(root, season) or raw.available_games(
            root, "boxscorematchupsv3", season
        )
    frames: list[pl.DataFrame] = []
    for gid, payload in raw.iter_game_payloads(root, "boxscorematchupsv3", game_ids):
        rows = matchup_rows(payload)
        if not rows:
            continue
        df = pl.DataFrame(rows, infer_schema_length=None, strict=False)
        df = df.rename({c: snake(c) for c in df.columns})
        frames.append(df.with_columns(game_id=pl.lit(gid), season=pl.lit(season)))
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")
