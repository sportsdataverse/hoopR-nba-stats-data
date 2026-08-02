import pytest
from nba_data_build.cache_guard import assert_pipeline_version


def test_guard_passes_on_current_main():
    # main is PIPELINE_VERSION 3 (Phase-B boundaries); guard returns it.
    assert assert_pipeline_version() >= 3


def test_guard_rejects_below_minimum():
    with pytest.raises(RuntimeError, match="PIPELINE_VERSION"):
        assert_pipeline_version(minimum=999)
