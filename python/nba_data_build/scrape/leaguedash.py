"""Season-level league-dash scrape for stats.nba.com / stats.wnba.com — the FULL
parameter cube of the ``leaguedash*`` endpoints.

The cube has two kinds of dimensions:

* **Schema-changing** (different columns entirely): ``measure_type`` (Base vs
  Advanced vs Misc ...), ``pt_measure_type`` (Drives vs Passing ...). Each such
  corner is its own :class:`Variant` -> its own table/release tag, so every
  table has one self-consistent column set.
* **Row-slice** (same columns, different rows): ``season_type`` (Regular Season
  + Playoffs), ``group_quantity`` (2/3/4/5-man lineups — probe-verified to share
  one schema), ``per_mode``. These are STACKED into the variant's table and
  tagged as columns (``season_type`` / ``group_quantity`` / ``per_mode``), so
  consumers filter instead of juggling table names.

``per_mode`` is pinned to ``Totals``: PerGame/Per36/Per100 are derivable
(stat / GP etc.) and Advanced measures are already rates — scraping them would
multiply the request budget for no information.

On top of the granular tables, :func:`build_mega` assembles wide per-entity
**mega tables** (``player_master`` / ``team_master`` / ``lineups_master``): the
Base variant is the spine and every other member is left-joined on the entity
keys with a column prefix (``adv_`` / ``bio_`` / ``drives_`` ...), so nothing
collides and one row carries every stat family for the entity-season.

Known upstream caveat (2026-07-11 probe): ``leaguedashlineups`` serves at most
**2000 rows per slice** (top lineups by playing time; NBA 2/3/4/5-man all hit
exactly 2000, WNBA 2-man = 965 uncapped). Per-team fetches
(``team_id_nullable``, 30 calls/slice) are the workaround if full lineup
coverage is ever needed.

All calls reuse the shared proxy pool (:class:`~nba_data_build.scrape.proxy.RoundRobin`)
and rate limiter (:class:`~nba_data_build.scrape.rate_limit.TokenBucket`) so this
traffic shares one stats.nba.com request budget with the per-game v3 scrape.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

import polars as pl

from .proxy import RoundRobin
from .rate_limit import TokenBucket

# Injectable for offline tests: (module, fn_name, kwargs) -> polars/pandas frame | dict.
Transport = Callable[[str, str, dict], Any]

SEASON_TYPES: tuple[str, ...] = ("Regular Season", "Playoffs")

# league -> (sdv-py module, wrapper prefix, LeagueID)
_LEAGUE: dict[str, tuple[str, str, str]] = {
    "nba": ("sportsdataverse.nba.nba_stats", "nba_stats", "00"),
    "wnba": ("sportsdataverse.wnba.wnba_stats", "wnba_stats", "10"),
}

_LINEUP_SLICES: tuple[Mapping[str, str], ...] = (
    {"group_quantity": "2"},
    {"group_quantity": "3"},
    {"group_quantity": "4"},
    {"group_quantity": "5"},
)


@dataclass(frozen=True)
class Variant:
    """One granular league-dash dataset: an endpoint pinned to one
    schema-defining corner of its parameter cube.

    Attributes:
        table: dataset name (release-tag suffix), e.g. ``"player_stats_advanced"``.
        slug: the ``nba_stats_``/``wnba_stats_`` wrapper suffix.
        entity_key: join key for mega assembly (``"player_id"`` / ``"team_id"`` /
            ``"group_id"``).
        params: schema-defining wrapper kwargs (measure type, per_mode, ...).
        season_type_param: wrapper kwarg carrying the season type (None = endpoint
            has no such kwarg).
        season_types: which season types to stack (standings: RS only).
        row_slices: extra row-slice fetches stacked + tagged as columns
            (lineups: one per ``group_quantity``).
        wnba: whether the endpoint exists on stats.wnba.com.
        mega: mega table this variant folds into (None = granular only).
        prefix: column prefix inside the mega (None = this variant IS the spine).
    """

    table: str
    slug: str
    entity_key: str
    params: Mapping[str, str] = field(default_factory=dict)
    season_type_param: Optional[str] = "season_type_all_star"
    season_types: tuple[str, ...] = SEASON_TYPES
    row_slices: tuple[Mapping[str, str], ...] = ({},)
    wnba: bool = True
    mega: Optional[str] = None
    prefix: Optional[str] = None


def _norm(value: str) -> str:
    """``"Four Factors"`` -> ``"fourfactors"``, ``"PullUpShot"`` -> ``"pullupshot"``."""
    return value.replace(" ", "").lower()


# Everything below is the survivor set of the 2026-07-11 cube probe (one real
# proxied call per corner; EMPTY corners excluded with a comment).

# player_stats: "Four Factors" + "Opponent" are team concepts -> EMPTY for players.
_PLAYER_MEASURES = ("Base", "Advanced", "Misc", "Scoring", "Usage", "Defense")
# team_stats: full measure set works (incl. the team-only Four Factors/Opponent).
_TEAM_MEASURES = (
    "Base",
    "Advanced",
    "Misc",
    "Four Factors",
    "Opponent",
    "Scoring",
    "Defense",
)
_LINEUP_MEASURES = ("Base", "Advanced", "Misc", "Four Factors", "Opponent", "Scoring")
_PT_CATEGORIES = (
    "Drives",
    "Defense",
    "CatchShoot",
    "Passing",
    "Possessions",
    "PullUpShot",
    "Rebounding",
    "Efficiency",
    "SpeedDistance",
    "ElbowTouch",
    "PostTouch",
    "PaintTouch",
)

# Mega column prefixes per measure type (Base is always the unprefixed spine).
_MEASURE_PREFIX = {
    "Advanced": "adv_",
    "Misc": "misc_",
    "Scoring": "scor_",
    "Usage": "usg_",
    "Defense": "def_",
    "Four Factors": "ff_",
    "Opponent": "opp_",
}


def variants(league: str) -> tuple[Variant, ...]:
    """The curated variant cube for ``league`` (player tracking is NBA-only)."""
    out: list[Variant] = []
    for m in _PLAYER_MEASURES:
        out.append(
            Variant(
                table=f"player_stats_{_norm(m)}",
                slug="leaguedashplayerstats",
                entity_key="player_id",
                params={
                    "measure_type_detailed_defense": m,
                    "per_mode_detailed": "Totals",
                },
                mega="player_master",
                prefix=None if m == "Base" else _MEASURE_PREFIX[m],
            )
        )
    out.append(
        Variant(
            table="player_bio",
            slug="leaguedashplayerbiostats",
            entity_key="player_id",
            params={"per_mode_simple": "Totals"},
            mega="player_master",
            prefix="bio_",
        )
    )
    for m in _TEAM_MEASURES:
        out.append(
            Variant(
                table=f"team_stats_{_norm(m)}",
                slug="leaguedashteamstats",
                entity_key="team_id",
                params={
                    "measure_type_detailed_defense": m,
                    "per_mode_detailed": "Totals",
                },
                mega="team_master",
                prefix=None if m == "Base" else _MEASURE_PREFIX[m],
            )
        )
    for m in _LINEUP_MEASURES:
        out.append(
            Variant(
                table=f"lineups_{_norm(m)}",
                slug="leaguedashlineups",
                entity_key="group_id",
                params={
                    "measure_type_detailed_defense": m,
                    "per_mode_detailed": "Totals",
                },
                row_slices=_LINEUP_SLICES,
                mega="lineups_master",
                prefix=None if m == "Base" else _MEASURE_PREFIX[m],
            )
        )
    if league == "nba":  # stats.wnba.com has no leaguedashptstats
        for c in _PT_CATEGORIES:
            out.append(
                Variant(
                    table=f"player_tracking_{_norm(c)}",
                    slug="leaguedashptstats",
                    entity_key="player_id",
                    params={"pt_measure_type": c, "per_mode_simple": "Totals"},
                    mega="player_master",
                    # "Defense" would collide with measure-type defense -> ptdef_
                    prefix="ptdef_" if c == "Defense" else f"{_norm(c)}_",
                )
            )
    out.append(
        Variant(
            table="standings",
            slug="leaguestandingsv3",
            entity_key="team_id",
            params={},
            season_type_param="season_type",
            season_types=("Regular Season",),
        )
    )
    return tuple(v for v in out if league == "nba" or v.wnba)


def megas(league: str) -> tuple[str, ...]:
    """Mega tables assemblable for ``league``, in build order."""
    return tuple(dict.fromkeys(v.mega for v in variants(league) if v.mega))


def season_str(year: int, league: str) -> str:
    """stats API season string: NBA ``2024`` -> ``"2023-24"``; WNBA ``2024`` -> ``"2024"``."""
    return f"{year - 1}-{str(year)[-2:]}" if league == "nba" else str(year)


def _default_transport(module: str, fn_name: str, kwargs: dict) -> Any:
    return getattr(importlib.import_module(module), fn_name)(**kwargs)


def _to_frame(raw: Any) -> pl.DataFrame:
    if isinstance(raw, dict):  # multi-result-set payload -> first set
        raw = next(iter(raw.values()), None)
    if raw is None:
        return pl.DataFrame()
    return raw if isinstance(raw, pl.DataFrame) else pl.from_pandas(raw)


class LeagueDashClient:
    """Proxy-rotated, rate-limited fetch of one :class:`Variant` per (league, season).

    Construct with the shared :class:`RoundRobin` + :class:`TokenBucket`;
    ``transport`` is injectable for offline tests. Each wire call retries once
    on a transient failure (matching the repo's retry-then-skip convention),
    then raises for the caller's per-(table, season) skip.
    """

    def __init__(
        self,
        proxies: RoundRobin,
        bucket: TokenBucket,
        *,
        transport: Optional[Transport] = None,
    ) -> None:
        self._proxies = proxies
        self._bucket = bucket
        self._transport = transport or _default_transport

    def _call(self, module: str, fn_name: str, kwargs: dict) -> Any:
        last: Optional[Exception] = None
        for _attempt in range(2):
            self._bucket.acquire()
            kwargs["proxy_url"] = self._proxies.next()
            try:
                return self._transport(module, fn_name, kwargs)
            except Exception as exc:  # noqa: BLE001 - retry once, then surface
                last = exc
        assert last is not None  # loop always ran twice
        raise last

    def fetch_variant(self, v: Variant, league: str, season: int) -> pl.DataFrame:
        """All row-slices of ``v`` for one (league, season), stacked + tagged.

        Tags: ``season`` (int end-year), ``league_id``, ``season_type``,
        ``per_mode`` (when the endpoint has one), and any row-slice keys
        (``group_quantity`` as int). Empty slices (e.g. Playoffs before they
        happen, tracking pre-2014) are skipped; an all-empty fetch returns an
        empty frame.
        """
        module, prefix, lid = _LEAGUE[league]
        per_mode = next(
            (val for key, val in v.params.items() if key.startswith("per_mode")), None
        )
        frames: list[pl.DataFrame] = []
        for st in v.season_types:
            for slice_params in v.row_slices:
                kwargs: dict[str, Any] = {
                    "season": season_str(season, league),
                    "league_id": lid,
                    **v.params,
                    **slice_params,
                }
                if v.season_type_param:
                    kwargs[v.season_type_param] = st
                df = _to_frame(self._call(module, f"{prefix}_{v.slug}", kwargs))
                if df.is_empty():
                    continue
                tags = [
                    pl.lit(season).alias("season"),
                    pl.lit(lid).alias("league_id"),
                    pl.lit(st).alias("season_type"),
                ]
                if per_mode:
                    tags.append(pl.lit(per_mode).alias("per_mode"))
                for key, val in slice_params.items():
                    tags.append(pl.lit(int(val) if val.isdigit() else val).alias(key))
                frames.append(df.with_columns(tags))
        return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()


def build_mega(
    mega: str, league: str, frames: dict[str, pl.DataFrame]
) -> Optional[pl.DataFrame]:
    """Assemble one wide mega table from a season's granular ``frames``.

    The ``prefix=None`` member is the spine; every other member is left-joined
    on the entity keys with ALL its non-key columns prefixed, so columns never
    collide and a missing member (empty season, WNBA without tracking) just
    contributes nothing. Returns None when the spine itself is absent.
    """
    members = [v for v in variants(league) if v.mega == mega]
    spine_v = next((v for v in members if v.prefix is None), None)
    if spine_v is None:
        return None
    spine = frames.get(spine_v.table)
    if spine is None or spine.is_empty():
        return None
    keys = [spine_v.entity_key, "season", "season_type", "league_id"]
    if spine_v.entity_key == "group_id":
        # group_id is a player-id composite, NOT team-unique: the same duo
        # traded together appears under two teams. team_id disambiguates.
        # (player/team spines must NOT add it — a traded player has one row
        # whose team can drift between scrape windows, nulling his joins.)
        keys.append("team_id")
    for s in spine_v.row_slices:  # slice tags join too (e.g. group_quantity), deduped
        for k in s:
            if k not in keys:
                keys.append(k)
    out = spine
    for v in members:
        if v.prefix is None:
            continue
        df = frames.get(v.table)
        if df is None or df.is_empty() or any(k not in df.columns for k in keys):
            continue
        stat_cols = [c for c in df.columns if c not in keys]
        renamed = df.select(keys + stat_cols).rename(
            {c: f"{v.prefix}{c}" for c in stat_cols}
        )
        out = out.join(renamed, on=keys, how="left")
    return out
