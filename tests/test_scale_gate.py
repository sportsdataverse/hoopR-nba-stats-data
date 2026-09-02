"""The SCALE gate: a correlation cannot see a rescale.

Every gate in FLOORS is a correlation or a row count, and both are invariant to
an affine rescale -- a season whose ratings all came out 10x too large passes
every one of them. That is how mis-scaled "xwOBA" of .44-.73 shipped on
2026-09-01 (baseballr-data 75d29ddbc5). These tests pin the level instead.
"""

import polars as pl
import pytest
from nba_model_publish.gates import SCALE_BANDS, SCALE_QUALIFY_POSS, scale_checks

_QUAL = SCALE_QUALIFY_POSS


def _season(scale: float = 1.0, n: int = 200) -> pl.DataFrame:
    """A plausible season, optionally rescaled by ``scale``."""
    rapm = [(-3.0 + 6.0 * i / (n - 1)) * scale for i in range(n)]
    return pl.DataFrame(
        {
            "rapm": rapm,
            "adj_rapm": [v * 2.5 for v in rapm],
            "off_poss": [_QUAL + 10] * n,
        }
    )


def test_a_plausible_season_passes():
    checks = scale_checks({2026: _season()})
    assert checks and all(c["status"] == "PASS" for c in checks), checks


@pytest.mark.parametrize("factor", [10.0, 0.05])
def test_a_rescaled_season_is_caught(factor):
    """The exact failure a correlation gate is blind to."""
    checks = scale_checks({2026: _season(scale=factor)})

    assert any(c["status"] == "FAIL" for c in checks), (
        f"a {factor}x rescale passed every scale band: {checks}"
    )
    # ... and it is the SPREAD that catches it, which is the point
    assert any(c["gate"].startswith("sd_") and c["status"] == "FAIL" for c in checks)


def test_correlation_really_is_blind_to_the_rescale():
    """Guards the premise: this is why a rank/correlation floor cannot catch it."""
    base = _season()
    scaled = _season(scale=10.0)

    r = pl.DataFrame({"a": base["rapm"], "b": scaled["rapm"]}).select(
        pl.corr("a", "b")
    ).item()

    assert r == pytest.approx(1.0, abs=1e-9)


def test_a_thin_season_is_skipped_not_passed():
    checks = scale_checks({2026: _season(n=5)})
    assert [c["status"] for c in checks] == ["SKIPPED"]


def test_every_band_is_two_sided_and_ordered():
    for name, (lo, hi) in SCALE_BANDS.items():
        assert lo < hi, name


def test_a_frame_without_the_level_columns_is_skipped_not_passed():
    """A build that drops off_poss must not silently satisfy the scale gate."""
    thin = pl.DataFrame({"rapm": [0.1] * 50, "adj_rapm": [0.25] * 50})

    checks = scale_checks({2026: thin})

    assert [c["status"] for c in checks] == ["SKIPPED"]
    assert "off_poss" in checks[0]["reason"]
