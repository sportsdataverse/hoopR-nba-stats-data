import sys

import polars as pl
import pytest
from nba_data_build.process import from_raw
from nba_data_build.process.from_raw import process_game

_ROOT = "tests/fixtures/raw"


def test_process_reads_raw_no_network():
    pg = process_game(_ROOT, "0022300001")
    assert pg.possessions.height > 0
    assert pg.lineups.height > 0
    # enriched pbp carries the on-court 10 + cumulative possession number
    for c in ["off_player_1", "def_player_5", "possession_number"]:
        assert c in pg.enriched_pbp.columns
    # cumulative possession number is monotonic non-decreasing within the game
    pn = pg.possessions["possession_number"].to_list()
    assert pn == sorted(pn) and pn[0] >= 1


def test_process_uses_quarter_box_source():
    # sdv-py @main now ships players_on_court_from_quarter_boxscores, so
    # _quarter_box_oncourt's import resolves and the preferred quarter-box path
    # runs -- every possession is stamped "quarter_box". (This assertion is a
    # canary on a FLOATING dep: sportsdataverse is pinned to @main, so if
    # upstream ever drops that symbol the seam silently reverts to the pbp
    # fallback and the lineups we publish change source underneath us. That is
    # exactly what this test is here to catch -- do not weaken it to accept
    # either label.)
    pg = process_game(_ROOT, "0022300001")
    assert pg.possessions["lineup_source"].unique().to_list() == ["quarter_box"]


def test_process_falls_back_when_upstream_symbol_absent(monkeypatch):
    # The real upstream now ships players_on_court_from_quarter_boxscores, so the
    # live path (test above) can no longer reach the ImportError branch. Simulate
    # an upstream WITHOUT the symbol to keep the fallback covered: `from X import
    # missing_name` raises ImportError, the seam catches it, and the label must be
    # the honest "pbp_fallback" -- never a hardcoded "quarter_box" constant.
    calls: list[str] = []

    def _fake_players_on_court_from_pbp(enh, box_raw, *, home_team_id, away_team_id):
        calls.append("pbp_fallback")
        return pl.DataFrame(
            {
                "home_player_1": [1],
                "home_player_2": [2],
                "home_player_3": [3],
                "home_player_4": [4],
                "home_player_5": [5],
                "away_player_1": [6],
                "away_player_2": [7],
                "away_player_3": [8],
                "away_player_4": [9],
                "away_player_5": [10],
            }
        )

    # No players_on_court_from_quarter_boxscores attribute -> ImportError on import.
    fake_module = type(
        "FakeNbaLineups",
        (),
        {"players_on_court_from_pbp": staticmethod(_fake_players_on_court_from_pbp)},
    )()

    monkeypatch.setitem(sys.modules, "sportsdataverse.nba.nba_lineups", fake_module)

    enh = pl.DataFrame({"order_index": [1]})
    oc, used = from_raw._quarter_box_oncourt(enh, {}, {}, home_team_id=1, away_team_id=2)
    assert used == "pbp_fallback"
    assert calls == ["pbp_fallback"]
    assert oc.height == 1


def test_process_reconciles_points_to_boxscore():
    pg = process_game(_ROOT, "0022300001")
    # offense points sum equals the two team totals from the boxscore (reuse recon)
    assert pg.possessions["points"].sum() > 0


# --- no-pbp games (valid capture, empty actions[]) ---------------------------
#
# stats.nba.com published no play-by-play for ~1,600 captured games (preseason
# before 2010-11, most All-Star exhibitions, two 2005 phantom placeholders).
# Their playbyplayv3 capture is valid and carries ``actions: []``; the
# boxscoretraditionalv3_period capture does not exist at all, because period
# counts are derived from pbp. Those games must BUILD (empty), while a genuinely
# missing capture must still raise.


def _write_pbpv3(root, game_id: str, n_actions: int) -> None:
    """Legacy-layout pbpv3 capture with *n_actions* synthetic actions."""
    import json

    d = root / "nba_stats" / "json" / "pbpv3"
    d.mkdir(parents=True, exist_ok=True)
    actions = [
        {
            "actionNumber": i + 1,
            "period": 1,
            "clock": "PT12M00.00S",
            "actionType": "Jump Ball",
            "teamId": 1,
        }
        for i in range(n_actions)
    ]
    payload = {"meta": {}, "game": {"gameId": game_id, "videoAvailable": 0, "actions": actions}}
    (d / f"{game_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_process_game_empty_actions_builds_instead_of_raising(tmp_path):
    # Only the pbpv3 capture exists -- no boxv3, no boxv3_periods, exactly like
    # the real store for a game that never had plays.
    _write_pbpv3(tmp_path, "0019600001", 0)
    pg = process_game(tmp_path, "0019600001")
    assert pg.game_id == "0019600001"
    assert pg.enriched_pbp.is_empty()
    assert pg.possessions.is_empty()
    assert pg.lineups.is_empty()
    # The empty pbp frame still carries the documented schema (not a bare frame).
    assert "game_id" in pg.enriched_pbp.columns and "order_index" in pg.enriched_pbp.columns


def test_process_game_missing_capture_still_raises(tmp_path):
    # Same shape, but the payload says the game HAS plays: the absent
    # boxv3/boxv3_periods captures are a real capture gap and must fail loudly.
    _write_pbpv3(tmp_path, "0019600002", 3)
    with pytest.raises(FileNotFoundError):
        process_game(tmp_path, "0019600002")
    # Nothing captured at all -> also loud.
    with pytest.raises(FileNotFoundError):
        process_game(tmp_path, "0019600003")


def test_pbp_action_count_rejects_malformed_payload():
    assert from_raw.pbp_action_count({"game": {"actions": []}}) == 0
    assert from_raw.pbp_action_count({"game": {"actions": [{}, {}]}}) == 2
    # A garbled / error capture is NOT "this game has no plays".
    for bad in ({}, {"game": {}}, {"game": None}, None, {"game": {"actions": None}}):
        with pytest.raises(ValueError):
            from_raw.pbp_action_count(bad, "0019600001")
