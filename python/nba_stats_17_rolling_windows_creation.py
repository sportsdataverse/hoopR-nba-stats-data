"""Stage 17 -- rolling_windows.

Thin shim over the tested build package: the pipeline logic lives in
``nba_data_build.reshape``; this file exists so the stage sequence is readable
from a directory listing.

Stage numbers follow the ``DATASETS`` registry order in
``nba_data_build/reshape/datasets.py``, which is the intended build order --
``rolling_windows`` (17) derives from ``shots`` (15) and builds before
``metric_curves`` (18).

Rolling shooting form (sdv-py ``sportsdataverse.rolling_windows``): every shooter's
last 50 / 200 field-goal and three-point attempts, against the window before, the
window entering the season and the career before it. Regular-season + playoff
attempts only, ids as text with ``id_source`` ``"nba_stats"``. Reads this run's
``shots`` frame when stage 15 is in the same invocation (the daily processor), else
the committed ``{--base}/shots/parquet/shots_{season}.parquet``; every earlier
committed shots season and ``{--base}/nba_stats_schedule_master.parquet`` supply
the career history and the game dates, so a standalone backfill needs no raw store
at all. Seasons are END years (1997 = 1996-97), the shots' span.

Equivalent to::

    python -m nba_data_build.reshape --datasets rolling_windows --seasons <year>
"""

from __future__ import annotations

import sys

from nba_data_build.reshape.cli import main

DATASET = "rolling_windows"

if __name__ == "__main__":
    # DATASET is appended, not prepended: argparse keeps the LAST occurrence of
    # an option, so a stray --datasets on the command line cannot make stage 17
    # build something other than rolling_windows.
    sys.exit(main([*sys.argv[1:], "--datasets", DATASET]))
