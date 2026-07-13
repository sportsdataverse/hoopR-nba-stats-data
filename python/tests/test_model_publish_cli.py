"""Hermetic tests for the nba_model_publish CLI (no network, no sportsdataverse import)."""

import argparse

import pytest

from nba_model_publish.cli import _parse_seasons, main


def test_parse_seasons_range_and_single():
    assert _parse_seasons("2022:2024") == [2022, 2023, 2024]
    assert _parse_seasons("2023") == [2023]


def test_parse_seasons_rejects_inverted_and_malformed():
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_seasons("2024:2022")
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_seasons("twenty:twentytwo")


def test_upload_subcommand_dry_run_is_network_free(tmp_path, capsys):
    (tmp_path / "nba_player_impact_2023.parquet").write_bytes(b"i23")
    (tmp_path / "nba_player_impact_2024.parquet").write_bytes(b"i24")
    (tmp_path / "unrelated.txt").write_text("ignored")
    rc = main(
        [
            "upload",
            "--dir",
            str(tmp_path),
            "--tag",
            "nba_player_impact",
            "--dry-run",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "uploaded=0" in out  # dry-run uploads nothing
    assert "files=2" in out  # only the two parquet files matched


def test_upload_subcommand_pattern_selects_card(tmp_path, capsys):
    (tmp_path / "nba_player_impact_2023.parquet").write_bytes(b"i23")
    (tmp_path / "nba_player_impact_card.json").write_text("{}")
    rc = main(
        [
            "upload",
            "--dir",
            str(tmp_path),
            "--tag",
            "nba_player_impact",
            "--pattern",
            "*_card.json",
            "--dry-run",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "files=1" in out
