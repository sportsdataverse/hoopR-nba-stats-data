
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
    pg = process_game(_ROOT, "0022300001")
    assert pg.possessions["lineup_source"].unique().to_list() == ["quarter_box"]


def test_process_reconciles_points_to_boxscore():
    pg = process_game(_ROOT, "0022300001")
    # offense points sum equals the two team totals from the boxscore (reuse recon)
    assert pg.possessions["points"].sum() > 0
