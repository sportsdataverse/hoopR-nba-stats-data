"""Registry of the published NBA stats datasets — the reshaper's contract.

Each entry names where a dataset comes from in the raw store and where it goes on
``sportsdataverse-data``, so the builders stay declarative and the release tags
live in one place rather than scattered across ten scripts.

``nba_type`` is not decoration: the R producers stamp it via
``hoopR:::make_hoopR_data(type, timestamp)`` and it is what ``print.hoopR_data``
shows as the header, so published artifacts keep identifying themselves the same way.

``season_floor`` is the first start-year season with real data for a dataset's source
endpoint (from the Phase 0 coverage probe). ``None`` means 1996 — the full history —
applies. A season below the floor produces no artifact rather than shipping an empty
release; only ``lineups`` (tracking-style lineup data begins 2007-08) has a floor
above 1996.

Datasets whose source is ``None`` are *derived* rather than reshaped from a single
endpoint (shots comes out of play-by-play), and are built by dedicated code.
"""

from __future__ import annotations

from typing import NamedTuple


class Dataset(NamedTuple):
    """One published dataset."""

    key: str
    #: Raw-store endpoint, or None when the dataset is derived from another.
    endpoint: str | None
    #: resultSet name within the payload; None takes the first non-empty set.
    result_set: str | None
    #: Released filename stem; the season is appended (``standings_2025``).
    stem: str
    release_tag: str
    #: Stamped as the rds's ``hoopR_type``.
    nba_type: str
    #: "season" = one payload per season; "game" = one per game, bound per season.
    level: str = "season"
    #: First start-year season with real data; None means the full history (1996).
    season_floor: int | None = None


_R = "from hoopR data repository"

DATASETS: tuple[Dataset, ...] = (
    Dataset(
        "standings",
        "leaguestandingsv3",
        None,
        "standings",
        "nba_stats_standings",
        f"NBA Stats League Standings V3 {_R}",
    ),
    Dataset(
        "player_season_stats",
        "leaguedashplayerstats",
        None,
        "player_season_stats",
        "nba_stats_player_season_stats",
        f"NBA Stats Player Season Stats {_R}",
    ),
    Dataset(
        "team_season_stats",
        "leaguedashteamstats",
        None,
        "team_season_stats",
        "nba_stats_team_season_stats",
        f"NBA Stats Team Season Stats {_R}",
    ),
    Dataset(
        "lineups",
        "leaguedashlineups",
        None,
        "lineups",
        "nba_stats_lineups",
        f"NBA Stats Lineups {_R}",
        season_floor=2007,
    ),
    Dataset(
        "rosters",
        "commonteamroster",
        "CommonTeamRoster",
        "rosters",
        "nba_stats_rosters",
        f"NBA Stats Rosters {_R}",
    ),
    Dataset(
        "coaches",
        "commonteamroster",
        "Coaches",
        "coaches",
        "nba_stats_coaches",
        f"NBA Stats Coaches {_R}",
    ),
    Dataset(
        "draft",
        "drafthistory",
        None,
        "draft",
        "nba_stats_draft",
        f"NBA Stats Draft History {_R}",
    ),
    Dataset(
        "schedules",
        "leaguegamelog",
        None,
        "nba_stats_schedule",
        "nba_stats_schedules",
        f"NBA Stats Schedule {_R}",
    ),
    Dataset(
        "player_game_logs",
        "leaguegamelog",
        None,
        "player_game_logs",
        "nba_stats_player_game_logs",
        f"NBA Stats Player Game Logs {_R}",
    ),
    # -- per-game, bound into one frame per season --------------------------------
    Dataset(
        "pbp",
        "playbyplayv3",
        None,
        "play_by_play",
        "nba_stats_pbp",
        f"NBA Stats Play-by-Play {_R}",
        level="game",
    ),
    Dataset(
        "game_rosters",
        "boxscoresummaryv2",
        "InactivePlayers",
        "game_rosters",
        "nba_stats_game_rosters",
        f"NBA Stats Game Rosters {_R}",
        level="game",
    ),
    Dataset(
        "officials",
        "boxscoresummaryv2",
        "Officials",
        "officials",
        "nba_stats_officials",
        f"NBA Stats Officials {_R}",
        level="game",
    ),
    Dataset(
        "player_boxscores",
        "boxscoretraditionalv3",
        None,
        "player_boxscores",
        "nba_stats_player_boxscores",
        f"NBA Stats Player Boxscores {_R}",
        level="game",
    ),
    Dataset(
        "team_boxscores",
        "boxscoretraditionalv3",
        None,
        "team_boxscores",
        "nba_stats_team_boxscores",
        f"NBA Stats Team Boxscores {_R}",
        level="game",
    ),
    # -- derived ------------------------------------------------------------------
    Dataset(
        "shots",
        None,
        None,
        "shots",
        "nba_stats_shots",
        f"NBA Stats Shots {_R}",
        level="derived",
    ),
)

BY_KEY: dict[str, Dataset] = {d.key: d for d in DATASETS}

#: Every release tag this repo publishes to.
RELEASE_TAGS: tuple[str, ...] = tuple(dict.fromkeys(d.release_tag for d in DATASETS))
