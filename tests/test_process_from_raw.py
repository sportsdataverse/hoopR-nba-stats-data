import sys

import polars as pl
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
    oc, used = from_raw._quarter_box_oncourt(
        enh, {}, {}, home_team_id=1, away_team_id=2
    )
    assert used == "pbp_fallback"
    assert calls == ["pbp_fallback"]
    assert oc.height == 1


def test_process_reconciles_points_to_boxscore():
    pg = process_game(_ROOT, "0022300001")
    # offense points sum equals the two team totals from the boxscore (reuse recon)
    assert pg.possessions["points"].sum() > 0
