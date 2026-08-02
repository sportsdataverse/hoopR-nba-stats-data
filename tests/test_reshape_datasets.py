"""Registry tests — the 15 NBA datasets, their tags, and the NBA-specific fields."""

from __future__ import annotations

from nba_data_build.reshape import datasets
from nba_data_build.reshape.datasets import BY_KEY, DATASETS, RELEASE_TAGS


def test_exactly_fifteen_datasets() -> None:
    assert len(DATASETS) == 15


def test_release_tags_are_nba_stats_and_unique() -> None:
    tags = [d.release_tag for d in DATASETS]
    assert all(t.startswith("nba_stats_") for t in tags)
    assert len(tags) == len(set(tags))
    assert RELEASE_TAGS == tuple(tags)


def test_lineups_maps_to_the_classic_tag_not_v3() -> None:
    d = BY_KEY["lineups"]
    assert d.release_tag == "nba_stats_lineups"  # NOT nba_stats_lineups_v3
    assert d.season_floor == 2007


def test_draft_endpoint_is_drafthistory() -> None:
    assert BY_KEY["draft"].endpoint == "drafthistory"


def test_only_lineups_has_a_floor_above_the_full_history() -> None:
    floored = {d.key: d.season_floor for d in DATASETS if d.season_floor is not None}
    assert floored == {"lineups": 2007}


def test_nba_type_strings_describe_the_repo() -> None:
    for d in DATASETS:
        assert d.nba_type.startswith("NBA Stats ")
        assert d.nba_type.endswith("from hoopR data repository")


def test_by_key_covers_every_dataset() -> None:
    assert set(BY_KEY) == {d.key for d in DATASETS}
    assert "possessions" not in BY_KEY
    assert "leaguedash" not in BY_KEY


def test_dataset_has_season_floor_field() -> None:
    assert "season_floor" in datasets.Dataset._fields
