"""Write built artifacts (parquet datasets + the markdown validation card)."""
from __future__ import annotations

from pathlib import Path

import polars as pl


def _ensure_parent(path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def write_possessions(poss: pl.DataFrame, path: Path) -> None:
    """Write a season's possession stint frame to parquet."""
    _ensure_parent(path)
    poss.write_parquet(path)


def write_rapm(ratings: pl.DataFrame, path: Path) -> None:
    """Write a season's RAPM ratings frame to parquet."""
    _ensure_parent(path)
    ratings.write_parquet(path)


def write_report(md: str, path: Path) -> None:
    """Write the rendered validation card (markdown)."""
    _ensure_parent(path)
    Path(path).write_text(md, encoding="utf-8")
