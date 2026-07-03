"""Guard: never let a pre-Phase-B possession compile-cache into a published bundle."""
from __future__ import annotations


def assert_pipeline_version(minimum: int = 3) -> int:
    """Assert the installed sdv-py possession pipeline is >= *minimum*.

    Phase-B possession boundaries require PIPELINE_VERSION >= 3. Any dataset
    written for publish/commit must clear this.

    Args:
        minimum: Lowest acceptable ``PIPELINE_VERSION``. Defaults to 3
            (Phase-B possession boundaries).

    Returns:
        The installed ``sportsdataverse.nba.nba_season_compile.PIPELINE_VERSION``.

    Raises:
        RuntimeError: If the installed ``PIPELINE_VERSION`` is below *minimum*.
    """
    from sportsdataverse.nba.nba_season_compile import PIPELINE_VERSION

    if PIPELINE_VERSION < minimum:
        raise RuntimeError(
            f"sdv-py PIPELINE_VERSION={PIPELINE_VERSION} < required {minimum} — "
            "refusing to build a publishable dataset from a pre-Phase-B compile cache. "
            "Sync sportsdataverse to a main commit at/after Phase B."
        )
    return PIPELINE_VERSION
