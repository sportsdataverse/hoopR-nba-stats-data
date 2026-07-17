"""Hermetic tests for the nba_model_publish CLI (no network, no sportsdataverse import)."""

import argparse

import pytest

import nba_model_publish.cli as cli
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


# ---------------------------------------------------------------------------
# Proxy resolution. Refusing to start beats hanging: an unattended run that
# silently lost its proxy would stall for hours on stats.nba.com, not error.
# ---------------------------------------------------------------------------


def test_resolve_proxy_provider_refuses_to_start_with_an_empty_pool(monkeypatch):
    monkeypatch.setattr("nba_data_build.scrape.proxy.load_proxies", lambda: [])
    with pytest.raises(SystemExit, match="no proxies available"):
        cli._resolve_proxy_provider(no_proxy=False)


def test_resolve_proxy_provider_rotates_the_pool(monkeypatch):
    monkeypatch.setattr(
        "nba_data_build.scrape.proxy.load_proxies",
        lambda: [
            {"ip": "1.1.1.1", "port": 8000, "login": "u", "password": "p"},
            {"ip": "2.2.2.2", "port": 8000, "login": "u", "password": "p"},
        ],
    )
    nxt = cli._resolve_proxy_provider(no_proxy=False)
    assert nxt() != nxt()  # successive calls hand out different exit IPs


def test_no_proxy_opts_out_explicitly():
    assert cli._resolve_proxy_provider(no_proxy=True) is None


def test_impact_delay_s_flag_and_env_default(monkeypatch):
    ns = cli.build_parser().parse_args(
        ["impact", "--seasons", "2023", "--out", "o", "--delay-s", "1.5"]
    )
    assert ns.delay_s == 1.5
    # env default is read at parser-build time, so re-build after setting it
    monkeypatch.setenv("SDV_NBA_DELAY_S", "7")
    ns = cli.build_parser().parse_args(["impact", "--seasons", "2023", "--out", "o"])
    assert ns.delay_s == 7.0
