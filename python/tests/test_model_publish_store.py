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


def test_variant_leaguegamelog_team_and_player_are_distinct_captures():
    """Team rows carry no PLAYER_ID, so the two variants are NOT interchangeable.
    The team capture keeps the bare name; the player top-up sits beside it as
    `_p`. Mapping a "P" call onto the team file would push team rows into
    player-log processing."""
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
        B._store_variant("leaguegamelog", {"player_or_team_abbreviation": "P"})
        == "regular-season_p"
    )
    assert (
        B._store_variant(
            "leaguegamelog",
            {"player_or_team_abbreviation": "P", "season_type_all_star": "Playoffs"},
        )
        == "playoffs_p"
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


def test_store_backed_player_and_team_read_different_captures(monkeypatch):
    """Both leaguegamelog calls are served offline, each from its OWN capture --
    a "P" call must never be handed the team file (no PLAYER_ID in it)."""
    seen: list = []

    def fake_reader(endpoint, season, variant, *, raw_store_dir):
        seen.append(variant)
        return pl.DataFrame({"player_id": [1]})

    monkeypatch.setattr(B, "nba_raw_store_season_frame", fake_reader)
    fetch = B._store_backed("leaguegamelog", _live_boom, None, "/store")
    fetch(season="2023-24", player_or_team_abbreviation="P")
    fetch(season="2023-24", player_or_team_abbreviation="T")
    assert seen == ["regular-season_p", "regular-season"]


def test_store_backed_without_store_is_plain_proxied():
    """No store configured -> byte-identical behaviour to the pre-existing path."""

    def live(**kw):
        return pl.DataFrame({"x": [1]})

    assert B._store_backed("playerindex", live, None, None) is live
