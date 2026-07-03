from nba_data_build.scrape.client import V3Client
from nba_data_build.scrape.orchestrate import scrape_finished_games, scrape_game
from nba_data_build.scrape.raw_store import has_raw


def _client():
    return V3Client(transport=lambda kind, game_id, **p: {"kind": kind, "game_id": game_id})


def test_scrape_game_writes_then_skips(tmp_path):
    c = _client()
    assert scrape_game(c, tmp_path, "0022300001", 4) is True
    assert has_raw(tmp_path, "0022300001")
    assert scrape_game(c, tmp_path, "0022300001", 4) is False  # resumable skip
    assert scrape_game(c, tmp_path, "0022300001", 4, rescrape=True) is True


def test_finished_game_filter(tmp_path):
    rows = [
        {"game_id": "0022300001", "game_status": 3, "home_team_id": 1610612744, "n_periods": 4},
        {"game_id": "0022300002", "game_status": 2, "home_team_id": 1610612745, "n_periods": 4},  # live -> skip
        {"game_id": "0022300003", "game_status": 3, "home_team_id": 0, "n_periods": 4},  # all-star/TBD -> skip
    ]
    written = scrape_finished_games(_client(), tmp_path, rows)
    assert written == ["0022300001"]
