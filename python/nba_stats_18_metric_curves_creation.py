"""Stage 18 -- metric_curves.

Thin shim over the tested build package: the pipeline logic lives in
``nba_data_build.reshape``; this file exists so the stage sequence is readable
from a directory listing.

Stage numbers follow the ``DATASETS`` registry order in
``nba_data_build/reshape/datasets.py``, which is the intended build order --
``metric_curves`` (18) derives from ``shots`` (15). Stage 17 is reserved for
``rolling_windows`` (F3b), which the roadmap orders before this one; a number is
a stable dataset identity, so the hole stays rather than being compacted.

FG% by shot distance (sdv-py ``sportsdataverse.metric_curves``) for the league,
every team and every shooter, per season: regular-season + playoff attempts only,
1-ft bins to 35 ft then 35-50 and 50-95, ids as text with ``id_source``
``"nba_stats"``. Reads this run's ``shots`` frame when stage 15 is in the same
invocation (the daily processor), else the committed
``{--base}/shots/parquet/shots_{season}.parquet`` -- so a standalone backfill
needs no raw store at all. Seasons are END years (1997 = 1996-97), the shots' span.

Equivalent to::

    python -m nba_data_build.reshape --datasets metric_curves --seasons <year>
"""

from __future__ import annotations

import sys

from nba_data_build.reshape.cli import main

DATASET = "metric_curves"

if __name__ == "__main__":
    # DATASET is appended, not prepended: argparse keeps the LAST occurrence of
    # an option, so a stray --datasets on the command line cannot make stage 18
    # build something other than metric_curves.
    sys.exit(main([*sys.argv[1:], "--datasets", DATASET]))
