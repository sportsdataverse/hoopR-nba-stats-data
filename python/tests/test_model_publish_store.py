"""Hermetic tests for the raw-store-backed season fetchers (no network).

These cover the seam that makes a GitHub Actions build possible: season-level
stats calls read the committed hoopR-nba-stats-raw captures (local dir or URL)
instead of stats.nba.com, falling through to live only on a genuine miss.
"""

from __future__ import annotations

import polars as pl
import pytest

from nba_model_publish import builders as B


# --- season label -> store season directory ---------------------------------


@pytest.mark.parametrize(
    "season,expected",
    [
        ("2023-24", 2024),
        ("1996-97", 1997),
        (2024, 2024),
        (None, None),
        ("", None),
        ("junk", None),
    ],
)
def test_season_end_year(season, expected):
    """The API takes the START-year label; the store is keyed by END year."""
    assert B._season_end_year(season) == expected


# --- variant mapping --------------------------------------------------------


def test_variant_playerindex_is_unparameterized():
    assert B._store_variant("playerindex", {}) == ""  # bare {endpoint}/{season}.json


def test_variant_biostats_combines_season_type_and_per_mode():
    assert B._store_variant("leaguedashplayerbiostats", {}) == "regular-season_totals"
    assert (
        B._store_variant(
            "leaguedashplayerbiostats",
            {"season_type_all_star": "Playoffs", "per_mode_simple": "PerGame"},
        )
        == "playoffs_pergame"
    )


def test_variant_leaguegamelog_team_serves_player_does_not():
    """The sweep captured only player_or_team="T" (team rows, no PLAYER_ID).
    Serving those for a "P" call would push team rows into player-log
    processing, so the player call MUST decline the store and go live."""
    assert B._store_variant("leaguegamelog", {}) == "regular-season"
    assert (
        B._store_variant("leaguegamelog", {"player_or_team_abbreviation": "T"})
        == "regular-season"
    )
    assert (
        B._store_variant("leaguegamelog", {"season_type_all_star": "Playoffs"})
        == "playoffs"
    )
    assert (
        B._store_variant("leaguegamelog", {"player_or_team_abbreviation": "P"}) is None
    )


# --- the fetch seam ---------------------------------------------------------


def _live_boom(**_kw):
    raise AssertionError("live fetch must not be called on a store hit")


def test_store_backed_serves_committed_capture(monkeypatch):
    frame = pl.DataFrame({"player_id": [1], "age": [25.0]})
    seen: dict = {}

    def fake_reader(endpoint, season, variant, *, raw_store_dir):
        seen.update(
            endpoint=endpoint, season=season, variant=variant, root=raw_store_dir
        )
        return frame

    monkeypatch.setattr(B, "nba_raw_store_season_frame", fake_reader)
    fetch = B._store_backed(
        "leaguedashplayerbiostats", _live_boom, None, "https://cdn/x"
    )
    out = fetch(season="2023-24", league_id="00")
    assert out.equals(frame)
    assert seen == {
        "endpoint": "leaguedashplayerbiostats",
        "season": 2024,
        "variant": "regular-season_totals",
        "root": "https://cdn/x",
    }


def test_store_backed_bare_variant_passes_none(monkeypatch):
    """An unparameterized endpoint must reach the reader as variant=None so it
    resolves {endpoint}/{season}.json, not {endpoint}/{season}/.json."""
    seen: dict = {}

    def fake_reader(endpoint, season, variant, *, raw_store_dir):
        seen["variant"] = variant
        return pl.DataFrame({"person_id": [7]})

    monkeypatch.setattr(B, "nba_raw_store_season_frame", fake_reader)
    B._store_backed("playerindex", _live_boom, None, "/store")(season="2023-24")
    assert seen["variant"] is None


def test_store_backed_falls_back_to_live_on_miss(monkeypatch):
    monkeypatch.setattr(B, "nba_raw_store_season_frame", lambda *a, **k: None)
    calls = []

    def live(**kwargs):
        calls.append(kwargs)
        return pl.DataFrame({"x": [1]})

    out = B._store_backed("playerindex", live, None, "/store")(season="2023-24")
    assert out.height == 1 and len(calls) == 1


def test_store_backed_player_log_call_bypasses_store(monkeypatch):
    """A "P" leaguegamelog call must go live even with a store configured."""
    monkeypatch.setattr(
        B,
        "nba_raw_store_season_frame",
        lambda *a, **k: pytest.fail("store must not serve P"),
    )
    calls = []
    fetch = B._store_backed(
        "leaguegamelog", lambda **kw: calls.append(kw) or pl.DataFrame(), None, "/store"
    )
    fetch(season="2023-24", player_or_team_abbreviation="P")
    assert len(calls) == 1


def test_store_backed_without_store_is_plain_proxied():
    """No store configured -> byte-identical behaviour to the pre-existing path."""

    def live(**kw):
        return pl.DataFrame({"x": [1]})

    assert B._store_backed("playerindex", live, None, None) is live
