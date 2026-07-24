"""``python -m nba_data_build.reshape`` entry point -> :func:`nba_data_build.reshape.cli.main`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
