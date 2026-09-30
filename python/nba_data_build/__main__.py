"""``python -m nba_data_build`` entry point: the modeling ``build`` CLI.

Both ``python -m nba_data_build build ...`` and the historical no-verb invocation
(e.g. ``python -m nba_data_build --seasons 2023 --out build_out``) route to
:func:`nba_data_build.cli.main`. The retired ``pipeline`` verb (``pipeline_cli``,
which wrote retired paths/tags) was deleted 2026-09-30.
"""

import sys

from .cli import main as _build_main


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "build":
        return _build_main(argv[1:])
    return _build_main(argv)


if __name__ == "__main__":
    sys.exit(main())
