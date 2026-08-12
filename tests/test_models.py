"""Typed schema declarations for the released datasets (spec D39).

The models declare the schema, not the rows: they are asserted frame-level at
the write chokepoint (``reshape.io.write_release_formats``), never row-by-row
(pydantic over a multi-million-row pbp frame is a performance trap).
"""

from __future__ import annotations

import glob
from pathlib import Path

import polars as pl
import pytest
from nba_data_build.models import MODELS, check_frame, check_stem, polars_schema
from nba_data_build.reshape.datasets import BY_KEY, DATASETS

REPO_ROOT = Path(__file__).resolve().parents[1]

# Datasets registered in DATASETS that have never published an asset, and so
# have no real parquet to derive a schema from. Empty since draft published
# (30 seasons, 1996-2025); its model is declared from the published
# draft_2025.parquet, not borrowed from the WNBA twin.
UNPUBLISHED: set[str] = set()

MASTERS = {"schedule_master", "games_in_data_repo"}


def test_every_published_dataset_has_a_model():
    assert set(MODELS) == ({d.key for d in DATASETS} - UNPUBLISHED) | MASTERS


@pytest.mark.parametrize("dataset", sorted(MODELS), ids=sorted(MODELS))
def test_polars_schema_is_derivable(dataset):
    assert len(polars_schema(dataset)) > 0


@pytest.mark.parametrize("dataset", sorted(MODELS), ids=sorted(MODELS))
def test_game_id_is_declared_utf8(dataset):
    """NBA game ids are zero-padded ("0022300001"); an int round-trip drops
    the "00" league prefix, so every dataset that carries game_id pins Utf8."""
    schema = polars_schema(dataset)
    if "game_id" in schema:
        assert schema["game_id"] == pl.Utf8, f"{dataset}: game_id is {schema['game_id']}"


def test_entity_ids_are_declared_int64():
    """team_id / person_id are numeric stats.nba.com ids (join keys)."""
    for dataset in sorted(MODELS):
        schema = polars_schema(dataset)
        for col in ("team_id", "person_id"):
            if col in schema:
                assert schema[col] == pl.Int64, f"{dataset}.{col} is {schema[col]}"


def test_model_rejects_type_coercion():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MODELS["pbp"](game_id=22300001)  # int where the padded Utf8 id is declared


def test_check_frame_accepts_a_matching_frame():
    frame = pl.DataFrame(schema=dict(polars_schema("officials")))
    assert check_frame("officials", frame) == []


def test_check_frame_reports_a_missing_column():
    frame = pl.DataFrame({"game_id": ["0022300001"]})
    problems = check_frame("officials", frame)
    assert any("missing column" in p for p in problems)


def test_check_frame_tolerates_widening_but_not_type_changes():
    """An Int32 season read back from an older asset is losslessly Int64; a
    stringly one is not."""
    base = dict(polars_schema("officials"))
    ok = pl.DataFrame(schema={**base, "official_id": pl.Int32})
    assert [p for p in check_frame("officials", ok) if "official_id" in p] == []
    bad = pl.DataFrame(schema={**base, "official_id": pl.Utf8})
    assert any("official_id" in p for p in check_frame("officials", bad))


def test_check_frame_tolerates_an_all_null_column():
    base = dict(polars_schema("officials"))
    frame = pl.DataFrame(schema={**base, "first_name": pl.Null})
    assert [p for p in check_frame("officials", frame) if "first_name" in p] == []


def test_check_stem_resolves_the_seasoned_write_stem():
    frame = pl.DataFrame(schema=dict(polars_schema("standings")))
    assert check_stem("standings_2025", frame) == []
    assert check_stem("standings_2025", pl.DataFrame()) != []
    # A stem no dataset claims is not an error.
    assert check_stem("not_a_dataset_2024", pl.DataFrame()) == []
    # draft is published and modelled now, so its stem DOES resolve and check.
    draft = pl.DataFrame(schema=dict(polars_schema("draft")))
    assert check_stem("draft_2024", draft) == []
    assert check_stem("draft_2024", pl.DataFrame()) != []


#: nba_stats/<key>/ trees that predate the reshape registry (the old hoopR
#: v2/v3 compile surface); their parquets are NOT this pipeline's output, so
#: checking the D39 model against them would compare two different contracts.
LEGACY_TREES = {"pbp", "schedules", "lineups"}


@pytest.mark.archive
@pytest.mark.parametrize(
    "dataset", sorted(set(MODELS) - MASTERS), ids=sorted(set(MODELS) - MASTERS)
)
def test_model_matches_the_committed_parquet(dataset):
    """The declared schema must describe what the pipeline actually writes."""
    if dataset in LEGACY_TREES:
        pytest.skip("committed tree is the pre-registry hoopR surface")
    spec = BY_KEY[dataset]
    built = sorted(
        glob.glob(str(REPO_ROOT / "nba_stats" / dataset / "parquet" / f"{spec.stem}_*.parquet"))
    )
    if not built:
        pytest.skip(f"no committed parquet for {dataset}")
    frame = pl.read_parquet(built[-1], n_rows=1)
    problems = [p for p in check_frame(dataset, frame) if "missing column" in p]
    assert problems == [], "\n".join(problems)


@pytest.mark.archive
@pytest.mark.parametrize("dataset", sorted(MASTERS), ids=sorted(MASTERS))
def test_master_model_matches_the_committed_parquet(dataset):
    path = REPO_ROOT / "nba_stats" / f"nba_stats_{dataset}.parquet"
    if not path.exists():
        pytest.skip("no committed master parquet")
    frame = pl.read_parquet(path, n_rows=1)
    assert check_frame(dataset, frame) == []
