import json
from pathlib import Path

from nba_data_build.scrape.raw_store import has_raw, raw_path, write_raw


def test_verbatim_write_and_path(tmp_path):
    payload = {"game": {"actions": [{"a": 1}]}}
    write_raw(tmp_path, "pbpv3", "0022300001", payload)
    p = raw_path(tmp_path, "pbpv3", "0022300001")
    assert p == Path(tmp_path) / "nba_stats" / "json" / "pbpv3" / "0022300001.json"
    assert json.loads(p.read_text()) == payload  # byte-verbatim round-trip


def test_has_raw_requires_all_three(tmp_path):
    write_raw(tmp_path, "pbpv3", "g", {})
    assert not has_raw(tmp_path, "g")
    write_raw(tmp_path, "boxv3", "g", {})
    write_raw(tmp_path, "boxv3_periods", "g", {})
    assert has_raw(tmp_path, "g")
