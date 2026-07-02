from nba_data_build.incremental import detect_missing_seasons


def test_gap_between_first_and_current():
    assert detect_missing_seasons(published={2021, 2022}, current=2024, first=2021) == [2023, 2024]


def test_all_present_returns_empty():
    assert detect_missing_seasons(published={2021, 2022, 2023}, current=2023, first=2021) == []


def test_empty_release_returns_full_range():
    assert detect_missing_seasons(published=set(), current=2023, first=2021) == [2021, 2022, 2023]


def test_ignores_published_outside_range():
    assert detect_missing_seasons(published={2019, 2021}, current=2022, first=2021) == [2022]
