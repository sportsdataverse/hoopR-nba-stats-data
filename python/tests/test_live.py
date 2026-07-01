from pathlib import Path
from tests.conftest import skip_if_no_live
import nba_data_build.build as B


@skip_if_no_live
def test_build_one_real_season(tmp_path: Path) -> None:
    # ONE small real slice would still be a full-season compile; keep opt-in + residential IP only.
    res = B.build_season(2023, cache_dir=str(tmp_path / "cache"))
    assert res.n_possessions > 0 and not res.rapm.is_empty()
