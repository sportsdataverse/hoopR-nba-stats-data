"""Tests for the season-level league-dash scrape (offline — injected transport)."""

from __future__ import annotations

import polars as pl

from nba_data_build.scrape.leaguedash import (
    Endpoint,
    LeagueDashClient,
    endpoints_for,
    season_str,
)
from nba_data_build.scrape.proxy import RoundRobin
from nba_data_build.scrape.rate_limit import TokenBucket


def _client(payload: object) -> LeagueDashClient:
    # empty proxy pool (next()->None) + a real (non-blocking, first-call) bucket
    return LeagueDashClient(
        RoundRobin([]), TokenBucket(), transport=lambda m, f, k: payload
    )


def test_season_str() -> None:
    assert season_str(2024, "nba") == "2023-24"
    assert season_str(2000, "nba") == "1999-00"  # zero-pad the tail
    assert season_str(2024, "wnba") == "2024"


def test_endpoints_for_wnba_excludes_player_tracking() -> None:
    nba = {e.table for e in endpoints_for("nba")}
    wnba = {e.table for e in endpoints_for("wnba")}
    assert "player_tracking" in nba
    assert "player_tracking" not in wnba
    assert {"player_stats", "player_bio", "lineups", "standings"} <= wnba


def test_fetch_tags_season_and_league() -> None:
    df = pl.DataFrame({"player_id": [1, 2], "pts": [10, 20]})
    out = _client(df).fetch(
        Endpoint("player_stats", "leaguedashplayerstats"), "nba", 2024
    )
    assert out["season"].to_list() == [2024, 2024]
    assert out["league_id"].to_list() == ["00", "00"]


def test_fetch_empty_returns_empty() -> None:
    assert _client(pl.DataFrame()).fetch(Endpoint("x", "y"), "nba", 2024).is_empty()


def test_fetch_dict_payload_takes_first_result_set() -> None:
    out = _client({"SetA": pl.DataFrame({"a": [1]})}).fetch(
        Endpoint("x", "y"), "wnba", 2024
    )
    assert out["league_id"].to_list() == ["10"]  # WNBA LeagueID tag
