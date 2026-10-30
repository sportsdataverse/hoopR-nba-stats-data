"""``injury_report``: the NBA's official injury report, one row per listing per published version.

The raw store keeps one JSON per report date, ``injury_report/{END}/{YYYY-MM-DD}.json``
(``{"date", "probed", "slots": [{"report_time", "url", "rows": [...]}]}``). The league
re-publishes the report many times a day, so a player appears once per version he is
listed in; ``report_datetime`` (naive US/Eastern) tells the versions apart.

Joined here, so readers need no name matching of their own:

* ``game_id`` / ``team_id``: the committed schedule master, on the game's date and the
  printed ``AWY@HOM`` tricodes; ``team_id`` from the printed team name.
* ``person_id`` / ``match_method``: the season's player boxscores, used as rosters only.
  Tried in order: ``exact`` (normalized full name on that team-season), ``family``
  (family name and first initial unique on that team-season, e.g. "Steph" for
  "Stephen"), ``league`` (name unique league-wide that season, e.g. after a trade),
  then ``roster`` (name on that team in the season's committed ``rosters``, which also
  lists players who have not played -- a season-long absence), else null.

``game_id`` is null when the printed game is not in the schedule on that date: a
postponed game (it is played later under its own date) or a playoff game that turned
out not to be needed.

The printed ``matchup`` and ``player_name`` publish as ``report_matchup`` ("CLE@ATL") and
``report_player_name`` ("James, LeBron"): they are formatted differently from the
stats-API columns of those names. A team that had not filed by a version is one row
with a null ``report_player_name`` and
``reason`` ``"NOT YET SUBMITTED"``; it is kept, since it is information in its own right.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from pathlib import Path

import polars as pl

from .raw import _read_json

ENDPOINT = "injury_report"
NOT_SUBMITTED = "NOT YET SUBMITTED"
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

#: Raw row fields, in published order.
RAW_COLUMNS = (
    "report_datetime",
    "game_date",
    "game_time",
    "matchup",
    "away_team_abbr",
    "home_team_abbr",
    "team",
    "player_name",
    "current_status",
    "reason",
    "category",
    "previous_status",
)

SCHEMA: dict[str, pl.DataType] = {
    "season": pl.Int64,
    "report_datetime": pl.Datetime("us"),
    "game_date": pl.Date,
    "game_time": pl.Utf8,
    "report_matchup": pl.Utf8,
    "away_team_abbr": pl.Utf8,
    "home_team_abbr": pl.Utf8,
    "team": pl.Utf8,
    "report_player_name": pl.Utf8,
    "current_status": pl.Utf8,
    "reason": pl.Utf8,
    "category": pl.Utf8,
    "previous_status": pl.Utf8,
    "game_id": pl.Utf8,
    "team_id": pl.Int64,
    "person_id": pl.Int64,
    "match_method": pl.Utf8,
}


def _key(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.'`-]", "", s)
    return " ".join(w for w in s.split() if w not in _SUFFIXES)


def _report_key(player_name: str) -> str:  # "Pippen Jr., Scotty" -> "scotty pippen"
    last, _, first = player_name.partition(",")
    return _key(f"{first} {last}")


def season_games(base: str | Path, season: int) -> pl.DataFrame:
    """The season's games from the committed schedule master: date, tricodes, ids and team names."""
    master = pl.read_parquet(Path(base) / "nba_stats_schedule_master.parquet")

    def side(s: str) -> pl.Expr:
        return pl.concat_str(pl.col(f"{s}_team_city"), pl.col(f"{s}_team_name"), separator=" ")

    return master.filter(pl.col("season") == season).select(
        pl.col("game_id").cast(pl.Utf8),
        pl.col("game_date_est").str.slice(0, 10).str.to_date().alias("game_date"),
        pl.col("away_team_tricode").alias("away_team_abbr"),
        pl.col("home_team_tricode").alias("home_team_abbr"),
        pl.col("away_team_id").cast(pl.Int64),
        pl.col("home_team_id").cast(pl.Int64),
        side("away").alias("away_team"),
        side("home").alias("home_team"),
    )


def read_reports(root: str | Path, season: int, dates: list[dt.date]) -> pl.DataFrame:
    """Every listing row in the raw files for ``dates`` (a missing date is skipped)."""
    rows = []
    for day in dates:
        payload = _read_json(root, f"{ENDPOINT}/{season}/{day.isoformat()}.json")
        for slot in (payload or {}).get("slots") or []:
            for r in slot.get("rows") or []:
                if r.get("player_name") or r.get("reason") == NOT_SUBMITTED:
                    rows.append({c: r.get(c) for c in RAW_COLUMNS})
    if not rows:
        return pl.DataFrame(schema={c: pl.Utf8 for c in RAW_COLUMNS})
    return pl.DataFrame(rows, schema={c: pl.Utf8 for c in RAW_COLUMNS})


def attach_ids(
    reports: pl.DataFrame,
    games: pl.DataFrame,
    box: pl.DataFrame,
    season: int,
    rosters: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Add ``game_id``, ``team_id``, ``person_id`` and ``match_method`` (see the module doc)."""
    on = ["game_date", "away_team_abbr", "home_team_abbr"]
    # team_id by printed name across the season, so a listing for a game not in the
    # schedule that day (postponed, Summer League) still matches on its team
    by_name = pl.concat(
        [
            games.select(pl.col(f"{s}_team").alias("team"), pl.col(f"{s}_team_id").alias("name_id"))
            for s in ("home", "away")
        ]
    ).unique()
    by_name = by_name.unique("team", keep="none")
    r = (
        reports.join(games, on=on, how="left")
        .join(by_name, on="team", how="left")
        .with_columns(
            pl.when(pl.col("team") == pl.col("home_team"))
            .then(pl.col("home_team_id"))
            .when(pl.col("team") == pl.col("away_team"))
            .then(pl.col("away_team_id"))
            .otherwise(pl.col("name_id"))
            .alias("team_id")
        )
    )
    family_key = pl.col("key").str.split(" ").list.last() + " " + pl.col("key").str.slice(0, 1)
    roster = (
        box.select(
            pl.col("team_id").cast(pl.Int64),
            pl.col("person_id").cast(pl.Int64),
            (pl.col("first_name").fill_null("") + " " + pl.col("family_name").fill_null(""))
            .map_elements(_key, return_dtype=pl.Utf8)
            .alias("key"),
        )
        .unique()
        .with_columns(family_key.alias("family"))
    )
    r = r.with_columns(
        pl.col("player_name").map_elements(_report_key, return_dtype=pl.Utf8).alias("key")
    ).with_columns(family_key.alias("family"))
    assert r.schema["team_id"] == roster.schema["team_id"]
    exact = roster.unique(["team_id", "key"], keep="none").select(
        "team_id", "key", pl.col("person_id").alias("p1")
    )
    family = (
        roster.unique(["team_id", "person_id"])
        .unique(["team_id", "family"], keep="none")
        .select("team_id", "family", pl.col("person_id").alias("p2"))
    )
    league = (
        roster.unique("person_id")
        .unique("key", keep="none")
        .select("key", pl.col("person_id").alias("p3"))
    )
    if rosters is None or rosters.is_empty():
        rosters = pl.DataFrame(
            schema={"team_id": pl.Int64, "player_id": pl.Int64, "player": pl.Utf8}
        )
    listed = (
        rosters.select(
            pl.col("team_id").cast(pl.Int64),
            pl.col("player_id").cast(pl.Int64).alias("p4"),
            pl.col("player").fill_null("").map_elements(_key, return_dtype=pl.Utf8).alias("key"),
        )
        .unique()
        .unique(["team_id", "key"], keep="none")
    )
    j = (
        r.join(exact, on=["team_id", "key"], how="left")
        .join(family, on=["team_id", "family"], how="left")
        .join(league, on="key", how="left")
        .join(listed, on=["team_id", "key"], how="left")
    )
    method = (
        pl.when(pl.col("p1").is_not_null())
        .then(pl.lit("exact"))
        .when(pl.col("p2").is_not_null())
        .then(pl.lit("family"))
        .when(pl.col("p3").is_not_null())
        .then(pl.lit("league"))
        .when(pl.col("p4").is_not_null())
        .then(pl.lit("roster"))
    )
    return j.with_columns(
        pl.lit(season).cast(pl.Int64).alias("season"),
        pl.coalesce("p1", "p2", "p3", "p4").alias("person_id"),
        method.alias("match_method"),
    )


def build_injury_report(
    root: str | Path,
    season: int,
    base: str | Path = "nba_stats",
    box: pl.DataFrame | None = None,
    today: dt.date | None = None,
) -> pl.DataFrame:
    """One season of ``injury_report`` (``SCHEMA``), sorted by version, game and team.

    Reads the raw file for every date of the season year, August 1 of the start year
    through July 31 of ``season`` (Summer League reports file in July), capped at
    ``today``; a date with no file is skipped. ``box`` is the season's player boxscores
    (this run's frame), else the committed
    ``{base}/player_boxscores/parquet/player_boxscores_{season}.parquet``; the
    ``roster`` fallback reads the committed ``{base}/rosters/parquet/rosters_{season}.parquet``.
    With neither, ``person_id`` is null.
    """
    games = season_games(base, season)
    if games.is_empty():
        return pl.DataFrame(schema=SCHEMA)
    first = dt.date(season - 1, 8, 1)
    last = min(dt.date(season, 7, 31), today or dt.date.today())
    dates = [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]
    reports = read_reports(root, season, dates)
    if reports.is_empty():
        return pl.DataFrame(schema=SCHEMA)
    reports = reports.with_columns(
        pl.col("report_datetime").str.to_datetime(time_unit="us"),
        pl.col("game_date").str.to_date(),
    )
    if box is None:
        path = Path(base) / "player_boxscores" / "parquet" / f"player_boxscores_{season}.parquet"
        cols = ["team_id", "person_id", "first_name", "family_name"]
        box = (
            pl.read_parquet(path, columns=cols)
            if path.is_file()
            else pl.DataFrame(schema=dict.fromkeys(cols, pl.Utf8))
        )
    roster_path = Path(base) / "rosters" / "parquet" / f"rosters_{season}.parquet"
    rosters = (
        pl.read_parquet(roster_path, columns=["team_id", "player_id", "player"])
        if roster_path.is_file()
        else None
    )
    out = attach_ids(reports, games, box, season, rosters).rename(
        {"matchup": "report_matchup", "player_name": "report_player_name"}
    )
    return (
        out.select(list(SCHEMA))
        .cast(SCHEMA)
        .sort(
            "report_datetime",
            "game_date",
            "report_matchup",
            "team",
            "report_player_name",
            nulls_last=True,
        )
    )
