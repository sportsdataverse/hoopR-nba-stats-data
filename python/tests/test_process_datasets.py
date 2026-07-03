import shutil

import polars as pl

from nba_data_build.process.datasets import rollup_season, write_game_cache
from nba_data_build.process.from_raw import ProcessedGame, process_game


def test_rollup_writes_three_datasets(tmp_path):
    # raw fixture lives under tests/fixtures/raw; write outputs into tmp_path
    shutil.copytree("tests/fixtures/raw/nba_stats", tmp_path / "nba_stats")
    paths = rollup_season(tmp_path, 2023, ["0022300001"], cache_root=tmp_path / "cache")
    assert set(paths) == {"pbpv3", "possessions", "lineups"}
    poss = pl.read_parquet(paths["possessions"])
    assert poss.height > 0 and poss["game_id"].dtype == pl.Utf8
    # round-trip: re-run reuses the game cache (no reprocess needed) and is identical
    paths2 = rollup_season(tmp_path, 2023, ["0022300001"], cache_root=tmp_path / "cache")
    assert pl.read_parquet(paths2["possessions"]).equals(poss)


def test_rollup_multi_game_diagonal_relaxed_merge(tmp_path):
    """Two games, one with a divergent per-game schema, exercised through a real rollup.

    Game B is a synthetic ``ProcessedGame`` whose possessions/lineups frames are
    missing the on-court player-slot columns entirely (an all-null-slot game --
    e.g. a game missing that lineup source, the exact scenario
    ``_coerce_id_dtypes``'s docstring calls out) and carries one extra column not
    present on Game A. It's pre-seeded into the game cache (``write_game_cache``)
    so ``rollup_season`` never needs a raw capture for it -- only Game A goes
    through the real ``process_game`` path.
    """
    shutil.copytree("tests/fixtures/raw/nba_stats", tmp_path / "nba_stats")
    game_a = process_game(tmp_path, "0022300001")

    slot_cols = [f"off_player_{i}" for i in range(1, 6)] + [f"def_player_{i}" for i in range(1, 6)]
    poss_b = (
        game_a.possessions.head(2)
        .drop(slot_cols)
        .with_columns(
            pl.lit("0022300002").alias("game_id"),
            pl.lit("pbp_fallback").alias("lineup_source"),
            pl.lit("synthetic_note").alias("extra_only_on_b"),
        )
    )
    lineups_b = game_a.lineups.head(2).with_columns(pl.lit("0022300002").alias("game_id"))
    enh_b = game_a.enriched_pbp.head(2).drop(slot_cols).with_columns(pl.lit("0022300002").alias("game_id"))
    game_b = ProcessedGame(game_id="0022300002", enriched_pbp=enh_b, possessions=poss_b, lineups=lineups_b)

    cache_root = tmp_path / "cache"
    write_game_cache(cache_root, 2023, game_b)

    paths = rollup_season(tmp_path, 2023, ["0022300001", "0022300002"], cache_root=cache_root)
    assert set(paths) == {"pbpv3", "possessions", "lineups"}

    poss = pl.read_parquet(paths["possessions"])
    assert set(poss["game_id"].unique().to_list()) == {"0022300001", "0022300002"}
    assert poss.height == game_a.possessions.height + 2
    # the column only Game B had survives the diagonal_relaxed concat (null for Game A's rows)
    assert "extra_only_on_b" in poss.columns
    assert poss.filter(pl.col("game_id") == "0022300001")["extra_only_on_b"].null_count() == game_a.possessions.height
    # Game B's all-missing slot columns widen through concat then get re-coerced to Int64 (not Null/Utf8)
    for c in slot_cols:
        assert poss.schema[c] == pl.Int64
    # lineup_source values from BOTH games survive into the possessions parquet
    assert set(poss["lineup_source"].unique().to_list()) >= {"pbp_fallback"}

    lineups = pl.read_parquet(paths["lineups"])
    assert set(lineups["game_id"].unique().to_list()) == {"0022300001", "0022300002"}
    assert lineups.height == game_a.lineups.height + 2

    pbpv3 = pl.read_parquet(paths["pbpv3"])
    assert set(pbpv3["game_id"].unique().to_list()) == {"0022300001", "0022300002"}
    assert pbpv3.height == game_a.enriched_pbp.height + 2
    for c in slot_cols:
        assert pbpv3.schema[c] == pl.Int64
