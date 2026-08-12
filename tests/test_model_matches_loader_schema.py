"""Cross-check the D39 models against sdv-py's loader schemas (spec 11.2).

The comparison data is a VENDORED fixture (``tests/fixtures/
loader_schemas_nba_stats.json``), not a read of the sibling sdv-py checkout --
CI has no sibling checkout, and the WBB pilot showed a sibling-path read
renders every page blank there. Refresh the fixture from a local sdv-py
checkout when its loader schemas are re-captured::

    python -c "import json, yaml; store = yaml.safe_load(open(
        '../sdv-py/tools/codegen/schemas/loader_schemas.yaml'));
        json.dump({k: v for k, v in store.items()
                   if k.startswith('load_nba_stats_')},
                  open('tests/fixtures/loader_schemas_nba_stats.json', 'w'),
                  indent=1)"

Column NAMES are the stable contract; dtypes are not compared because the
loader schemas record the captured dtype of a particular asset vintage
(Int32 season vs the model's declared Int64, etc.).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nba_data_build.models import MODELS, polars_schema
from nba_data_build.reshape.datasets import DATASETS

FIXTURE = Path(__file__).parent / "fixtures" / "loader_schemas_nba_stats.json"

#: Model columns the loader snapshot may legitimately lack: the D34 ``in_*``
#: availability flags are stamped after the vintage the schemas captured.
ALLOWED_MODEL_EXTRAS = {f"in_{d.key}" for d in DATASETS if d.level == "game"}


def _loaders() -> dict[str, list[dict]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_ships_with_the_tests():
    assert FIXTURE.exists()
    assert len(_loaders()) >= 10


def _mapped() -> list[str]:
    loaders = _loaders()
    return sorted(k for k in MODELS if f"load_nba_stats_{k}" in loaders)


@pytest.mark.parametrize("dataset", _mapped(), ids=_mapped())
def test_model_columns_match_the_loader_schema(dataset):
    loader_cols = {c["name"] for c in _loaders()[f"load_nba_stats_{dataset}"]}
    model_cols = set(polars_schema(dataset))
    missing = loader_cols - model_cols
    extra = (model_cols - loader_cols) - ALLOWED_MODEL_EXTRAS
    assert missing == set(), f"{dataset}: loader columns absent from the model: {sorted(missing)}"
    assert extra == set(), f"{dataset}: model columns unknown to the loader: {sorted(extra)}"


def test_every_loader_backed_dataset_is_cross_checked():
    """Every registry dataset sdv-py has a loader for must be in the mapping
    (a silently unmapped dataset would make this file vacuous)."""
    expected = {d.key for d in DATASETS if f"load_nba_stats_{d.key}" in _loaders()}
    assert set(_mapped()) == expected
    assert len(expected) >= 10
