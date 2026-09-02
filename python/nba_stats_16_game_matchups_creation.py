"""Stage 16 -- game_matchups.

Thin shim over the tested build package: the pipeline logic lives in
``nba_data_build.reshape``; this file exists so the stage sequence is readable
from a directory listing.

Stage numbers follow the ``DATASETS`` registry order in
``nba_data_build/reshape/datasets.py``, which is the intended build order.
``game_matchups`` was added after the original fifteen and is appended to the
registry rather than slotted beside the other per-game datasets, because a
number is a stable dataset identity -- inserting in the middle would renumber
shims that already exist.

Matchup tracking begins in 2017-18 (``season_floor=2017``); earlier seasons are
skipped before the build rather than shipping an empty asset.

Equivalent to::

    python -m nba_data_build.reshape --datasets game_matchups --seasons <year>
"""

from __future__ import annotations

import sys

from nba_data_build.reshape.cli import main

DATASET = "game_matchups"

if __name__ == "__main__":
    # DATASET is appended, not prepended: argparse keeps the LAST occurrence of
    # an option, so a stray --datasets on the command line cannot make stage 16
    # build something other than game_matchups.
    sys.exit(main([*sys.argv[1:], "--datasets", DATASET]))
