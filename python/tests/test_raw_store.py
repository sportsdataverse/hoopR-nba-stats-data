import json
from pathlib import Path

import pytest

from nba_data_build.scrape.raw_store import (
    has_raw,
    legacy_raw_path,
    period_paths,
    raw_path,
    read_raw,
    resolve_raw_path,
    season_of,
    write_raw,
)


def test_season_of_is_the_end_year():
    """An NBA season spans two calendar years; the store keys on the later one."""
    assert season_of("0022300001") == 2024
    assert season_of("0020500469") == 2006
    assert season_of("0029600001") == 1997  # 19xx branch


def test_verbatim_write_lands_in_the_shared_layout(tmp_path):
    payload = {"game": {"actions": [{"a": 1}]}}
    write_raw(tmp_path, "pbpv3", "0022300001", payload)
    p = raw_path(tmp_path, "pbpv3", "0022300001")
    assert p == Path(tmp_path) / "nba_stats" / "json" / "playbyplayv3" / "2024" / "0022300001.json"
    assert json.loads(p.read_text()) == payload


def test_reads_back_what_it_wrote(tmp_path):
    write_raw(tmp_path, "boxv3", "0022300001", {"b": 2})
    assert read_raw(tmp_path, "boxv3", "0022300001") == {"b": 2}


def test_legacy_layout_is_still_readable(tmp_path):
    """Committed fixtures and the pre-existing 40k-file store use the old paths."""
    legacy = legacy_raw_path(tmp_path, "pbpv3", "0022300001")
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"old": True}))
    assert resolve_raw_path(tmp_path, "pbpv3", "0022300001") == legacy
    assert read_raw(tmp_path, "pbpv3", "0022300001") == {"old": True}


def test_shared_layout_wins_over_legacy(tmp_path):
    legacy = legacy_raw_path(tmp_path, "pbpv3", "0022300001")
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"which": "legacy"}))
    write_raw(tmp_path, "pbpv3", "0022300001", {"which": "shared"})
    assert read_raw(tmp_path, "pbpv3", "0022300001") == {"which": "shared"}


def test_period_boxscores_are_reassembled_from_per_period_files(tmp_path):
    """Legacy kept every period in one file; the shared store splits them.

    Callers expect the {period: payload} mapping either way.
    """
    d = Path(tmp_path) / "nba_stats" / "json" / "boxscoretraditionalv3_period" / "2006"
    d.mkdir(parents=True)
    for period in (1, 2, 10):
        (d / f"0020500469_p{period}.json").write_text(json.dumps({"p": period}))
    assert [p.name for p in period_paths(tmp_path, "0020500469")] == [
        "0020500469_p1.json",
        "0020500469_p2.json",
        "0020500469_p10.json",  # numeric ordering, not lexical
    ]
    assert read_raw(tmp_path, "boxv3_periods", "0020500469") == {
        1: {"p": 1}, 2: {"p": 2}, 10: {"p": 10}
    }


def test_missing_capture_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_raw(tmp_path, "pbpv3", "0022300001")


def test_has_raw_requires_all_kinds(tmp_path):
    assert not has_raw(tmp_path, "0022300001")
    for kind in ("pbpv3", "boxv3", "boxv3_periods"):
        write_raw(tmp_path, kind, "0022300001", {})
    assert has_raw(tmp_path, "0022300001")


def test_has_raw_accepts_split_periods(tmp_path):
    """A game whose periods came from the shared store still counts as complete."""
    write_raw(tmp_path, "pbpv3", "0020500469", {})
    write_raw(tmp_path, "boxv3", "0020500469", {})
    d = Path(tmp_path) / "nba_stats" / "json" / "boxscoretraditionalv3_period" / "2006"
    d.mkdir(parents=True, exist_ok=True)
    (d / "0020500469_p1.json").write_text("{}")
    assert has_raw(tmp_path, "0020500469")
