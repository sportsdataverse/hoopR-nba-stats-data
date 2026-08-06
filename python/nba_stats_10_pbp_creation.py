"""Stage 10 -- pbp.

Thin shim over the tested build package: the pipeline logic lives in
``nba_data_build.reshape``; this file exists so the stage sequence is readable
from a directory listing.

Stage numbers follow the ``DATASETS`` registry order in
``nba_data_build/reshape/datasets.py``, which is the intended build order --
``shots`` (15) derives from ``pbp`` (10). The number is a stable dataset
identity, NOT an execution schedule: the daily driver builds every dataset in
one ``reshape`` invocation and remains the sequence truth.

Equivalent to::

    python -m nba_data_build.reshape --datasets pbp --seasons <year>
"""

from __future__ import annotations

import sys

from nba_data_build.reshape.cli import main

DATASET = "pbp"

if __name__ == "__main__":
    # DATASET is appended, not prepended: argparse keeps the LAST occurrence of
    # an option, so a stray --datasets on the command line cannot make stage 10
    # build something other than pbp.
    sys.exit(main([*sys.argv[1:], "--datasets", DATASET]))
