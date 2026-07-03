"""``python -m nba_data_build`` entry point: routes to a verb sub-CLI.

``pipeline`` -> :func:`nba_data_build.pipeline_cli.main` (Tasks 4-10: scrape -> process
-> rollup -> flags, controller-gated publish). Anything else (including the historical
no-verb invocation, e.g. ``python -m nba_data_build --seasons 2023 --out build_out``)
falls through to the existing modeling ``build`` path,
:func:`nba_data_build.cli.main`, unchanged -- this keeps every pre-existing script and
doc example working verbatim.
"""

import sys

from .cli import main as _build_main
from .pipeline_cli import main as _pipeline_main


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "pipeline":
        return _pipeline_main(argv[1:])
    if argv and argv[0] == "build":
        return _build_main(argv[1:])
    return _build_main(argv)


if __name__ == "__main__":
    sys.exit(main())
