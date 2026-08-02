"""From-raw processor: enhanced pbp -> quarter-box lineups -> possessions.

Rebuilds one game's compiled surface entirely from the verbatim raw store
(:mod:`~nba_data_build.scrape.raw_store`) -- **no network, no ``V3Client``**.
Consumes the pinned sdv-py possession engine (``PIPELINE_VERSION`` >= 3,
guarded by :func:`~nba_data_build.cache_guard.assert_pipeline_version`):
``enhanced_pbp_from_payload`` -> on-court lineup reconstruction ->
``build_possessions`` -> ``attach_possession_lineups``.

Quarter-box lineup seam
------------------------
The on-court reconstruction uses sdv-py's quarter-box lineup engine
(``players_on_court_from_quarter_boxscores``, built from the ``boxv3_periods``
raw capture). It was written before that function landed upstream, so
:func:`_quarter_box_oncourt` is a seam: it imports the upstream function
opportunistically and falls back to the gamerotation-free
``players_on_court_from_pbp`` (boxscore starters + play-by-play substitutions
only -- no ``boxv3_periods`` needed) when the symbol is absent.

**The symbol has since landed**, so the preferred quarter-box path is what
actually runs today and the fallback is dormant. The seam is deliberately kept:
``sportsdataverse`` is pinned to ``@main`` (a FLOATING git dep), so the branch
taken here is decided by whatever upstream happens to ship. That is precisely
why the label must stay derived, never hardcoded.

**Provenance**: :func:`_quarter_box_oncourt` returns ``(oncourt_frame, used)``
and :func:`process_game` stamps ``lineup_source`` from the threaded *used*
value -- ``"quarter_box"`` when the upstream import resolved and ran,
``"pbp_fallback"`` when the ``ImportError`` fallback path ran (mirrors the
``used`` pattern in sdv-py's ``nba_possessions.nba_possessions``). Because the
dep floats, ``lineup_source`` is the *only* record of which engine produced a
given row -- it is a real provenance column, not a debug flag. Both branches are
pinned by tests (``test_process_from_raw.py``); if upstream ever drops the
symbol, published lineups silently change source and those tests are what catch
it. See ``.superpowers/sdd/pipeline/task-7-report.md`` for the full writeup.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

import polars as pl

from ..cache_guard import assert_pipeline_version
from ..scrape.raw_store import read_raw


@dataclass
class ProcessedGame:
    """One game's from-raw-compiled surface.

    Attributes:
        game_id: 10-digit NBA Stats game id.
        enriched_pbp: Enhanced pbp v3 events with the on-court 10
            (``off_player_1..5`` / ``def_player_1..5``) and the running
            ``possession_number`` attached to every event.
        possessions: One row per possession (``build_possessions`` +
            ``attach_possession_lineups`` output), plus ``lineup_source``.
        lineups: The raw on-court reconstruction frame (``LINEUPS_SCHEMA``:
            one row per action, home/away-keyed).
    """

    game_id: str
    enriched_pbp: pl.DataFrame
    possessions: pl.DataFrame
    lineups: pl.DataFrame


def _load_raw_json(root: Union[str, Path], kind: str, game_id: str) -> Any:
    """Read one verbatim raw capture from disk (never fetches).

    Delegates to :func:`~nba_data_build.scrape.raw_store.read_raw`, which resolves
    either store layout -- so this reads hoopR-nba-stats-raw's shared tree as
    happily as the legacy one here, and reassembles split per-period boxscores.
    """
    return read_raw(root, kind, game_id)


def _quarter_box_oncourt(
    enh: pl.DataFrame,
    periods: dict[int, Any],
    box_raw: dict[str, Any],
    *,
    home_team_id: int,
    away_team_id: int,
) -> "tuple[pl.DataFrame, str]":
    """Reconstruct the on-court 10 for the ``quarter_box`` lineup source.

    Seam: prefers sdv-py's ``players_on_court_from_quarter_boxscores`` (built
    from *periods*, the ``boxv3_periods`` capture) when it exists upstream;
    falls back to the shipped gamerotation-free ``players_on_court_from_pbp``
    (boxscore starters + pbp substitutions, needs only *box_raw*) otherwise.
    See the module docstring for why the fallback exists. Mirrors the
    ``used`` pattern in sdv-py's ``nba_possessions.nba_possessions``
    (``_from_pbp``/``_from_rotation``, nba_possessions.py:948-980): the
    caller must stamp ``lineup_source`` from the returned label, never a
    hardcoded constant, so the label always reflects which path actually ran.

    Args:
        enh: Output of ``enhanced_pbp_from_payload``.
        periods: ``{period_int: boxscoretraditionalv3_dict}`` from the
            ``boxv3_periods`` raw capture, int-keyed.
        box_raw: Raw whole-game ``boxscoretraditionalv3`` dict.
        home_team_id: Home team id (from ``boxscore_home_away``).
        away_team_id: Away team id (from ``boxscore_home_away``).

    Returns:
        A ``(oncourt_frame, used)`` tuple: *oncourt_frame* has schema
        ``LINEUPS_SCHEMA``; *used* is ``"quarter_box"`` when the upstream
        ``players_on_court_from_quarter_boxscores`` import resolved and ran,
        or ``"pbp_fallback"`` when the ``ImportError`` fallback path ran.
    """
    try:
        from sportsdataverse.nba.nba_lineups import (  # type: ignore[attr-defined]
            players_on_court_from_quarter_boxscores,
        )
    except ImportError:
        from sportsdataverse.nba.nba_lineups import players_on_court_from_pbp

        oc = players_on_court_from_pbp(
            enh, box_raw, home_team_id=home_team_id, away_team_id=away_team_id
        )
        return oc, "pbp_fallback"
    oc = players_on_court_from_quarter_boxscores(
        enh, periods, home_team_id=home_team_id, away_team_id=away_team_id
    )
    return oc, "quarter_box"


def _attach_running_possession(enh: pl.DataFrame, poss: pl.DataFrame) -> pl.DataFrame:
    """Attach each possession's ``possession_number`` + on-court 10 to its events.

    Maps *poss*'s ``[start_order_index, end_order_index]`` ranges onto
    *enh*'s per-event ``order_index`` via an as-of backward join, then masks
    out any event past its matched possession's ``end_order_index`` (guards
    order_index gaps / pre-first-possession events -- e.g. the opening
    jump ball -- rather than silently misattributing them).

    Args:
        enh: Output of ``enhanced_pbp_from_payload``.
        poss: Output of ``attach_possession_lineups`` (possessions + the
            on-court 10 + ``possession_number``).

    Returns:
        *enh* with ``possession_number``, ``off_player_1..5``, and
        ``def_player_1..5`` appended (nullable -- unmatched events are null).
    """
    lineup_cols = [f"off_player_{i}" for i in range(1, 6)] + [
        f"def_player_{i}" for i in range(1, 6)
    ]
    attach_cols = ["possession_number", *lineup_cols]

    poss_for_join = poss.select(
        ["start_order_index", "end_order_index", *attach_cols]
    ).sort("start_order_index")
    enh_sorted = enh.sort("order_index")

    joined = enh_sorted.join_asof(
        poss_for_join, left_on="order_index", right_on="start_order_index"
    )

    out_of_range = pl.col("end_order_index").is_null() | (
        pl.col("order_index") > pl.col("end_order_index")
    )
    joined = joined.with_columns(
        [
            pl.when(out_of_range).then(None).otherwise(pl.col(c)).alias(c)
            for c in attach_cols
        ]
    )
    return joined.drop(["start_order_index", "end_order_index"])


def process_game(root: Union[str, Path], game_id: str) -> ProcessedGame:
    """Rebuild one game's enriched pbp + possessions + lineups from saved raw only.

    Reads the three verbatim raw captures (``pbpv3`` / ``boxv3`` /
    ``boxv3_periods``) written by :mod:`~nba_data_build.scrape.orchestrate`
    and runs them through the pinned sdv-py possession engine. Never fetches
    -- a missing raw capture raises ``FileNotFoundError`` rather than
    reaching for the network.

    Args:
        root: Raw-store root directory (see
            :func:`~nba_data_build.scrape.raw_store.raw_path`).
        game_id: 10-digit NBA Stats game id.

    Returns:
        A :class:`ProcessedGame` for *game_id*.

    Raises:
        RuntimeError: If the installed sdv-py ``PIPELINE_VERSION`` is below
            the Phase-B minimum (see
            :func:`~nba_data_build.cache_guard.assert_pipeline_version`).
        FileNotFoundError: If any of the three raw captures is missing on disk.

    Example:
        Quick start::

            from nba_data_build.process.from_raw import process_game
            pg = process_game("tests/fixtures/raw", "0022300001")
            print(pg.possessions.shape, pg.enriched_pbp.columns)
    """
    assert_pipeline_version()

    from sportsdataverse.nba.nba_enhanced_pbp import enhanced_pbp_from_payload
    from sportsdataverse.nba.nba_lineups import boxscore_home_away
    from sportsdataverse.nba.nba_possessions import (
        attach_possession_lineups,
        build_possessions,
    )

    pbpv3 = _load_raw_json(root, "pbpv3", game_id)
    boxv3 = _load_raw_json(root, "boxv3", game_id)
    boxv3_periods_raw = _load_raw_json(root, "boxv3_periods", game_id)
    # GOTCHA (Task 6): dict keys round-trip through JSON as strings -- int-cast them.
    periods = {int(k): v for k, v in boxv3_periods_raw.items()}

    enh = enhanced_pbp_from_payload(pbpv3)
    home, away = boxscore_home_away(boxv3)
    oc, used = _quarter_box_oncourt(
        enh, periods, boxv3, home_team_id=home, away_team_id=away
    )

    poss = attach_possession_lineups(
        build_possessions(enh), oc, enh, home_team_id=home
    ).with_columns(pl.lit(used).alias("lineup_source"))

    enriched_pbp = _attach_running_possession(enh, poss)

    return ProcessedGame(
        game_id=str(game_id),
        enriched_pbp=enriched_pbp,
        possessions=poss,
        lineups=oc,
    )
