"""Reader tests for the reshape raw store.

Most run against a synthetic tree so they work anywhere; the real-store tests use the
sibling ``hoopR-nba-stats-raw`` checkout when present and skip otherwise, so CI without
the sibling still passes. The load-bearing assertion: every store dir -- per-game and
season-level alike -- is the season END year, so ``dir = season`` with no shift.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nba_data_build.reshape import raw

REAL_STORE = Path("/mnt/sdv_repos/hoopR-nba-stats-raw/nba_stats/json")
needs_real_store = pytest.mark.skipif(
    not REAL_STORE.is_dir(), reason="sibling hoopR-nba-stats-raw checkout not present"
)


def _write(root: Path, rel: str, payload: object) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")


# -- end-year dirs (unit) -----------------------------------------------------------


def test_game_payload_path_uses_end_year_dir() -> None:
    p = raw.game_payload_path("/store", "playbyplayv3", "0021300001")
    assert p == Path("/store/playbyplayv3/2014/0021300001.json")


# -- real store (skips without the sibling checkout) --------------------------------


@needs_real_store
def test_game_endpoint_season_2013_resolves_under_end_year_dir() -> None:
    """A 2013-14 game must be found in the 2014 (end-year) directory."""
    gid = "0021300001"
    expected = REAL_STORE / "playbyplayv3" / "2014" / f"{gid}.json"
    assert raw.game_payload_path(REAL_STORE, "playbyplayv3", gid) == expected
    payload = raw.read_game(REAL_STORE, "playbyplayv3", gid)
    assert isinstance(payload, dict)
    assert payload.get("game", {}).get("actions"), "expected play-by-play actions"


@needs_real_store
def test_league_endpoint_season_2014_resolves_under_end_year_dir() -> None:
    """A league endpoint reads the end-year dir (2014 = 2013-14), no shift."""
    payload = raw.read_season(REAL_STORE, "leaguestandingsv3", 2014, "regular-season")
    assert isinstance(payload, dict)


@needs_real_store
def test_available_games_enumerates_a_real_season() -> None:
    games = raw.available_games(REAL_STORE, "playbyplayv3", 2014)
    assert games, "expected captured play-by-play for 2013-14"
    assert all(g.isdigit() and len(g) == 10 for g in games)


@needs_real_store
def test_iter_game_payloads_yields_a_real_payload() -> None:
    games = raw.available_games(REAL_STORE, "playbyplayv3", 2014)[:3]
    got = list(raw.iter_game_payloads(REAL_STORE, "playbyplayv3", games))
    assert got, "expected at least one real payload"
    gid, payload = got[0]
    assert isinstance(payload, dict) and gid.isdigit()


@needs_real_store
def test_season_game_ids_indexes_a_real_season() -> None:
    ids = raw.season_game_ids(REAL_STORE, 2014)
    assert ids and all(len(i) == 10 for i in ids)
    # The season-level index must hold the SAME season as the per-game dirs: every
    # id in leaguegamelog/2014 decodes to end year 2014 (fails on a START-keyed store).
    assert {raw.game_season_of(i) for i in ids} == {2014}


# -- offline behaviour --------------------------------------------------------------


def test_missing_payload_returns_none(tmp_path: Path) -> None:
    """A gap must read as None, not raise — sweeps are always partially complete."""
    assert raw.read_game(tmp_path, "playbyplayv3", "0021300001") is None
    assert raw.read_season(tmp_path, "leaguestandingsv3", 2014) is None


def test_corrupt_payload_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "playbyplayv3" / "2014" / "0021300001.json"
    p.parent.mkdir(parents=True)
    p.write_text("{not json", encoding="utf-8")
    assert raw.read_game(tmp_path, "playbyplayv3", "0021300001") is None


def test_read_season_variant_paths(tmp_path: Path) -> None:
    _write(tmp_path, "leaguedashlineups/2014/base_playoffs.json", {"ok": 1})
    _write(tmp_path, "leaguestandingsv3/2014.json", {"ok": 2})
    assert raw.read_season(tmp_path, "leaguedashlineups", 2014, "base_playoffs") == {
        "ok": 1
    }
    assert raw.read_season(tmp_path, "leaguestandingsv3", 2014) == {"ok": 2}
    assert raw.season_payload(tmp_path, "leaguestandingsv3", 2014) == {"ok": 2}


def test_available_games_reads_the_season_dir_unshifted(tmp_path: Path) -> None:
    _write(tmp_path, "playbyplayv3/2014/0021300001.json", {"a": 1})
    assert raw.available_games(tmp_path, "playbyplayv3", 2014) == ["0021300001"]
    # no +1/-1 shift: a neighbouring dir must not be consulted
    assert raw.available_games(tmp_path, "playbyplayv3", 2013) == []


def test_season_game_ids_unions_both_season_types(tmp_path: Path) -> None:
    def log(ids):
        return {
            "resultSets": [
                {"headers": ["GAME_ID", "X"], "rowSet": [[i, 1] for i in ids]}
            ]
        }

    _write(
        tmp_path,
        "leaguegamelog/2014/regular-season.json",
        log(["0021300001", "0021300002"]),
    )
    _write(tmp_path, "leaguegamelog/2014/playoffs.json", log(["0041300001"]))
    assert raw.season_game_ids(tmp_path, 2014) == [
        "0021300001",
        "0021300002",
        "0041300001",
    ]


def test_season_game_ids_zero_pads(tmp_path: Path) -> None:
    """stats.com sometimes returns the id as an int, which drops the leading zeros."""
    _write(
        tmp_path,
        "leaguegamelog/2014/regular-season.json",
        {"resultSets": [{"headers": ["GAME_ID"], "rowSet": [[21300001]]}]},
    )
    assert raw.season_game_ids(tmp_path, 2014) == ["0021300001"]


def test_iter_game_payloads_skips_misses(tmp_path: Path) -> None:
    _write(tmp_path, "playbyplayv3/2014/0021300001.json", {"a": 1})
    got = list(
        raw.iter_game_payloads(tmp_path, "playbyplayv3", ["0021300001", "0021300002"])
    )
    assert got == [("0021300001", {"a": 1})]


def test_result_set_named_and_default() -> None:
    payload = {
        "resultSets": [
            {"name": "Empty", "headers": ["A"], "rowSet": []},
            {"name": "Rows", "headers": ["A", "B"], "rowSet": [[1, 2]]},
        ]
    }
    assert raw.result_set(payload, "Rows") == (["A", "B"], [[1, 2]])
    # no name -> first non-empty set, so a leading empty set doesn't mask the data
    assert raw.result_set(payload) == (["A", "B"], [[1, 2]])
    assert raw.result_set(payload, "Empty") == (["A"], [])


def test_result_set_tolerates_garbage() -> None:
    assert raw.result_set(None) == ([], [])
    assert raw.result_set({}) == ([], [])
    assert raw.result_set({"resultSets": {}}) == ([], [])


def test_available_games_rejects_url_roots() -> None:
    """GitHub serves files, not listings — fail loudly rather than return nothing."""
    with pytest.raises(ValueError, match="local root"):
        raw.available_games(raw.RAW_BASE, "playbyplayv3", 2013)


def _http_error(code: int) -> raw.urllib.error.HTTPError:
    return raw.urllib.error.HTTPError(
        "https://raw.githubusercontent.com/x", code, "boom", {}, None
    )


def test_a_404_is_absence_but_a_transient_is_not(monkeypatch: pytest.MonkeyPatch) -> None:
    """Absence and failure must stay distinguishable over HTTP.

    A season reads ~1,300 per-game payloads from raw.githubusercontent, so
    mapping a 5xx / rate-limit / timeout to "never captured" drops that game
    from a PUBLISHED season on a green run. Only 404/410 may return None.
    """
    monkeypatch.setattr(raw.time, "sleep", lambda _s: None)
    monkeypatch.setenv("SDV_PY_HTTP_RETRIES", "2")

    def _raise(code: int):
        def _open(url, timeout: int = 60):
            raise _http_error(code)

        return _open

    monkeypatch.setattr(raw.urllib.request, "urlopen", _raise(404))
    assert raw._read_json(raw.RAW_BASE, "playbyplayv3/2025/0022400001.json") is None

    for code in (500, 502, 403):
        monkeypatch.setattr(raw.urllib.request, "urlopen", _raise(code))
        with pytest.raises(raw.urllib.error.HTTPError):
            raw._read_json(raw.RAW_BASE, "playbyplayv3/2025/0022400001.json")


def test_a_transient_recovers_within_the_retry_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(raw.time, "sleep", lambda _s: None)
    monkeypatch.setenv("SDV_PY_HTTP_RETRIES", "3")
    calls: list[int] = []

    class _Resp:
        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

        def read(self) -> bytes:
            return b'{"ok": 1}'

    def _flaky_then_ok(url, timeout: int = 60):
        calls.append(1)
        if len(calls) < 3:
            raise _http_error(503)
        return _Resp()

    monkeypatch.setattr(raw.urllib.request, "urlopen", _flaky_then_ok)
    assert raw._read_json(raw.RAW_BASE, "leaguestandingsv3/2025.json") == {"ok": 1}
    assert len(calls) == 3
