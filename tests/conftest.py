import os

import pytest

skip_if_no_live = pytest.mark.skipif(
    os.environ.get("SDV_PY_NBA_STATS_LIVE") != "1",
    reason="set SDV_PY_NBA_STATS_LIVE=1 to run live stats.nba.com compile from a residential IP",
)
