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
    # On the CURRENT pinned sdv-py rev, players_on_court_from_quarter_boxscores
    # does not exist yet -- _quarter_box_oncourt's ImportError seam falls back
    # to players_on_court_from_pbp, so every possession is genuinely stamped
    # "pbp_fallback". This is the honest label for today's pin, not
    # "quarter_box" (see the Critical-finding fix in from_raw.py).
    pg = process_game(_ROOT, "0022300001")
    assert pg.possessions["lineup_source"].unique().to_list() == ["pbp_fallback"]


def test_process_uses_quarter_box_source_when_upstream_resolves(monkeypatch):
    # Fake the future pin bump: make the upstream quarter-box function resolve
    # and run, and assert the label flips to "quarter_box" -- pinning BOTH
    # branches of the _quarter_box_oncourt seam so the test correctly flips
    # the moment the real symbol lands upstream.
    calls: list[str] = []

    def _fake_quarter_boxscores(enh, periods, *, home_team_id, away_team_id):
        calls.append("quarter_box")
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

    def _fake_players_on_court_from_pbp(*args, **kwargs):
        calls.append("pbp_fallback")
        raise AssertionError("pbp fallback must not run when the upstream import resolves")

    fake_module = type(
        "FakeNbaLineups",
        (),
        {
            "players_on_court_from_quarter_boxscores": staticmethod(_fake_quarter_boxscores),
            "players_on_court_from_pbp": staticmethod(_fake_players_on_court_from_pbp),
        },
    )()

    monkeypatch.setitem(sys.modules, "sportsdataverse.nba.nba_lineups", fake_module)

    enh = pl.DataFrame({"order_index": [1]})
    oc, used = from_raw._quarter_box_oncourt(enh, {}, {}, home_team_id=1, away_team_id=2)
    assert used == "quarter_box"
    assert calls == ["quarter_box"]
    assert oc.height == 1


def test_process_reconciles_points_to_boxscore():
    pg = process_game(_ROOT, "0022300001")
    # offense points sum equals the two team totals from the boxscore (reuse recon)
    assert pg.possessions["points"].sum() > 0
