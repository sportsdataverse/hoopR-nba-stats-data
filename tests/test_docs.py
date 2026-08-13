"""Generated dataset documentation (spec D40/D43).

Descriptions are authored for this league and ship with the package -- never
read from a sibling checkout (CI has none) and never borrowed from another
sport's schema store, which in the WBB pilot produced `assists` = "Assisted
tackles" (NFL) and `team_id` = a 247Sports recruiting key.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from nba_data_build.docs import (
    BUILDER,
    MASTERS,
    PAGES,
    _descriptions,
    _without_status,
    column_table,
    dataset_page,
    summary_table,
)
from nba_data_build.models import MODELS, polars_schema

#: Text that would betray a description borrowed from another sport.
_FOREIGN_MARKERS = (
    "tackle",
    "half-inning",
    "inning",
    "247sports",
    "quarterback",
    "nflverse",
    "transfer player",
    "recruit",
    "puck",
    "goalie",
    "pitcher",
    "batter",
    "touchdown",
    "yardage",
    "on3",
)

#: The highest-value surfaces carry full authored coverage; the long-tail
#: leaderboard datasets keep honest empty cells.
_FULLY_DESCRIBED = ("pbp", "schedules", "schedule_master", "games_in_data_repo")


def test_the_store_ships_with_the_package():
    """CI has no sibling sdv-py checkout; the store must live in-package."""
    from nba_data_build import docs as docs_mod

    assert Path(docs_mod.__file__).with_name("column_descriptions.yaml").exists()


@pytest.mark.parametrize("dataset", _FULLY_DESCRIBED, ids=_FULLY_DESCRIBED)
def test_high_value_datasets_are_fully_described(dataset):
    descriptions = _descriptions()
    missing = sorted(c for c in polars_schema(dataset) if not descriptions.get(c))
    assert missing == [], f"{dataset}: columns with no description: {missing}"


@pytest.mark.parametrize("dataset", sorted(MODELS), ids=sorted(MODELS))
def test_no_description_is_borrowed_from_another_sport(dataset):
    descriptions = _descriptions()
    offenders = {
        column: text
        for column in polars_schema(dataset)
        if (text := descriptions.get(column))
        and any(marker in text.lower() for marker in _FOREIGN_MARKERS)
    }
    assert offenders == {}, f"{dataset}: descriptions from another sport: {offenders}"


def test_every_page_has_a_builder_entry():
    """A dataset with no builder would render a broken link."""
    assert set(BUILDER) == set(PAGES)


@pytest.mark.parametrize("dataset", sorted(PAGES), ids=sorted(PAGES))
def test_dataset_page_renders(dataset):
    page = dataset_page(dataset, live=False)
    assert page.startswith(f"# `{dataset}`")
    assert BUILDER[dataset] in page
    assert "## Columns" in page


@pytest.mark.parametrize("dataset", sorted(PAGES), ids=sorted(PAGES))
def test_column_table_is_a_markdown_table_or_an_honest_note(dataset):
    table = column_table(dataset)
    if dataset in MODELS:
        assert table.startswith("| col_name | type | description |")
    else:
        assert table.startswith("_")


def test_summary_table_lists_every_page():
    block = summary_table(live=False)
    for dataset in PAGES:
        assert f"docs/datasets/{dataset}.md" in block


def test_masters_are_documented():
    """The stage-99 artifacts are first-class documented surfaces (D34)."""
    assert set(MASTERS) <= set(PAGES)
    page = dataset_page("games_in_data_repo", live=False)
    assert "in_*" in page or "in_pbp" in page


def test_pbp_page_explains_the_games_without_play_by_play():
    """`games built` < `games known` is coverage, not a backlog -- say so on the page."""
    page = dataset_page("pbp", live=False)
    assert "Preseason play-by-play begins with the 2010-11 season" in page
    assert "do not re-scrape them" in page
    # The gate must still see it: a note dropped from the generator is drift.
    assert "Preseason play-by-play" in _without_status(page)


def test_drift_gate_ignores_publish_status_and_coverage():
    page = dataset_page("pbp", live=False)
    noisy = page.replace(
        "| **Last published** | — (newest release asset) |",
        "| **Last published** | 2026-01-01 (newest release asset) |",
    )
    assert _without_status(page) == _without_status(noisy)
    assert _without_status(page) != _without_status(page.replace("`action_number`", "`gone`"))
