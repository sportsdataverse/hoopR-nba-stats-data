"""Tests for the league-dash cube scrape (offline — injected transport)."""

from __future__ import annotations

import polars as pl
import pytest

from nba_data_build.scrape.leaguedash import (
    LeagueDashClient,
    Variant,
    build_mega,
    megas,
    season_str,
    variants,
)
from nba_data_build.scrape.proxy import RoundRobin
from nba_data_build.scrape.rate_limit import TokenBucket


def _client(transport) -> LeagueDashClient:
    # empty proxy pool (next()->None) + a real (non-blocking, first-call) bucket
    return LeagueDashClient(RoundRobin([]), TokenBucket(n_hits=1), transport=transport)


def test_season_str() -> None:
    assert season_str(2024, "nba") == "2023-24"
    assert season_str(2000, "nba") == "1999-00"  # zero-pad the tail
    assert season_str(2024, "wnba") == "2024"


def test_variant_cube_shape() -> None:
    nba = variants("nba")
    wnba = variants("wnba")
    # 6 player measures + bio + 7 team measures + 6 lineup measures + 12 tracking + standings
    assert len(nba) == 6 + 1 + 7 + 6 + 12 + 1
    # WNBA = same minus the 12 tracking categories
    assert len(wnba) == len(nba) - 12
    assert not any(v.table.startswith("player_tracking") for v in wnba)
    assert {"player_stats_base", "team_stats_fourfactors", "lineups_opponent"} <= {
        v.table for v in nba
    }


def test_each_mega_has_one_spine_and_unique_prefixes() -> None:
    for league in ("nba", "wnba"):
        for mega in megas(league):
            members = [v for v in variants(league) if v.mega == mega]
            spines = [v for v in members if v.prefix is None]
            assert len(spines) == 1, f"{league}/{mega} needs exactly one spine"
            prefixes = [v.prefix for v in members if v.prefix is not None]
            assert len(prefixes) == len(set(prefixes)), (
                f"{league}/{mega} prefix collision"
            )


def test_fetch_variant_stacks_and_tags_slices() -> None:
    calls: list[dict] = []

    def transport(module: str, fn: str, kwargs: dict):
        calls.append(dict(kwargs))
        return pl.DataFrame({"group_id": ["g1"], "pts": [10]})

    v = next(x for x in variants("nba") if x.table == "lineups_base")
    out = _client(transport).fetch_variant(v, "nba", 2024)
    # 2 season types x 4 group quantities = 8 calls, stacked
    assert len(calls) == 8
    assert out.height == 8
    assert set(out["group_quantity"].to_list()) == {2, 3, 4, 5}
    assert set(out["season_type"].to_list()) == {"Regular Season", "Playoffs"}
    assert out["per_mode"].unique().to_list() == ["Totals"]
    assert out["season"].unique().to_list() == [2024]
    assert out["league_id"].unique().to_list() == ["00"]
    assert calls[0]["season"] == "2023-24"


def test_fetch_variant_retries_once_then_raises() -> None:
    boom_once = {"n": 0}

    def flaky(module: str, fn: str, kwargs: dict):
        boom_once["n"] += 1
        if boom_once["n"] == 1:
            raise TimeoutError("transient")
        return pl.DataFrame({"player_id": [1]})

    v = next(x for x in variants("nba") if x.table == "player_bio")
    out = _client(flaky).fetch_variant(v, "nba", 2024)
    assert out.height >= 1  # first call retried, rest succeed

    def always(module: str, fn: str, kwargs: dict):
        raise TimeoutError("down")

    with pytest.raises(TimeoutError):
        _client(always).fetch_variant(v, "nba", 2024)


def _tagged(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        pl.lit(2024).alias("season"),
        pl.lit("00").alias("league_id"),
        pl.lit("Regular Season").alias("season_type"),
    )


def test_build_mega_prefixes_and_left_joins() -> None:
    frames = {
        "player_stats_base": _tagged(
            pl.DataFrame({"player_id": [1, 2], "pts": [30, 20]})
        ),
        "player_stats_advanced": _tagged(
            pl.DataFrame({"player_id": [1], "off_rating": [118.0]})
        ),
        "player_bio": _tagged(
            pl.DataFrame({"player_id": [1, 2], "height": ["6-7", "6-1"]})
        ),
    }
    out = build_mega("player_master", "nba", frames)
    assert out is not None
    assert out.height == 2  # spine rows preserved
    assert {"pts", "adv_off_rating", "bio_height"} <= set(out.columns)
    # left join: player 2 has no advanced row -> null
    assert out.filter(pl.col("player_id") == 2)["adv_off_rating"].to_list() == [None]


def test_build_mega_requires_spine() -> None:
    only_adv = {
        "player_stats_advanced": _tagged(pl.DataFrame({"player_id": [1], "x": [1]}))
    }
    assert build_mega("player_master", "nba", only_adv) is None


def test_build_mega_lineups_joins_on_group_quantity() -> None:
    def lu(rows: dict) -> pl.DataFrame:
        return _tagged(pl.DataFrame(rows))

    frames = {
        # same group_id under two quantities AND two teams (duo traded
        # together, e.g. Olynyk-Agbaji UTA->TOR) must NOT cross-join
        "lineups_base": lu(
            {
                "group_id": ["g", "g", "g"],
                "team_id": [10, 10, 20],
                "group_quantity": [2, 5, 2],
                "pts": [1, 2, 3],
            }
        ),
        "lineups_advanced": lu(
            {
                "group_id": ["g", "g", "g"],
                "team_id": [10, 10, 20],
                "group_quantity": [2, 5, 2],
                "pace": [99.0, 101.0, 95.0],
            }
        ),
    }
    out = build_mega("lineups_master", "nba", frames)
    assert out is not None
    assert out.height == 3  # no join inflation: team_id is a lineup key
    two = out.filter((pl.col("group_quantity") == 2) & (pl.col("team_id") == 10))
    assert two["adv_pace"].to_list() == [99.0]


def test_build_megas_assemble_from_disk_state(tmp_path) -> None:
    # a re-run whose scrapes ALL fail must still rebuild full-width megas
    # from the prior run's on-disk granular files (convergent, no downgrade)
    from nba_data_build.leaguedash_cli import build

    tag_dir = tmp_path / "wnba_stats_leaguedash"
    tag_dir.mkdir(parents=True)
    _tagged(pl.DataFrame({"player_id": [1], "pts": [30]})).write_parquet(
        tag_dir / "player_stats_base_2024.parquet"
    )
    _tagged(pl.DataFrame({"player_id": [1], "off_rating": [118.0]})).write_parquet(
        tag_dir / "player_stats_advanced_2024.parquet"
    )

    def always_fail(module: str, fn: str, kwargs: dict):
        raise TimeoutError("down")

    written = build([2024], ["wnba"], tmp_path, client=_client(always_fail))
    assert written == {"wnba_stats_leaguedash/player_master": 1}
    mega = pl.read_parquet(tag_dir / "player_master_2024.parquet")
    assert {"pts", "adv_off_rating"} <= set(mega.columns)


def test_fetch_variant_dict_payload_and_empty() -> None:
    v = Variant(table="x", slug="leaguedashplayerbiostats", entity_key="player_id")
    out = _client(
        lambda m, f, k: {"SetA": pl.DataFrame({"player_id": [1]})}
    ).fetch_variant(v, "wnba", 2024)
    assert out["league_id"].unique().to_list() == ["10"]
    empty = _client(lambda m, f, k: pl.DataFrame()).fetch_variant(v, "wnba", 2024)
    assert empty.is_empty()
