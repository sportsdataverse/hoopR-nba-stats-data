#!/usr/bin/env python3
"""Phase 0 v3 coverage probe for the NBA reshaper port.

Scans the unified NBA raw store (``hoopR-nba-stats-raw``) and reports, per
source endpoint and per **start-year** season 1996-2026, how many raw files are
present and how many carry real rows vs are "empty 200" payloads. From that it
derives a **season floor** per endpoint: the first start-year season with real
populated data. Those floors feed ``reshape/datasets.py`` ``season_floor`` so
pre-floor seasons ship no artifact rather than an empty release.

Season <-> directory mapping (both live in this store, verified):

* **Game endpoints** (one ``{game_id}.json`` per game) key their season dir by
  the season **end** year: ``season_of(game_id) = start + 1``. Start-year season
  ``S`` is read from dir ``S + 1`` (game ``0021300001`` (2013-14) -> dir ``2014``).
  Endpoints: ``playbyplayv3``, ``boxscoresummaryv2``, ``boxscoretraditionalv3``.

* **League/season endpoints** key their season dir by the season **start** year
  directly (``leaguestandingsv3/2013`` -> ``SeasonYear=2013`` = 2013-14; a dir
  may hold several ``{variant}.json`` files). Start-year season ``S`` is read
  from dir ``S``. Endpoints: ``leaguestandingsv3``, ``leaguedashplayerstats``,
  ``leaguedashteamstats``, ``leaguedashlineups``, ``commonteamroster``,
  ``leaguegamelog``, ``drafthistory``.

Emptiness is judged by ``payload_rows`` across the three v3 payload shapes:
the ``resultSets`` envelope, the pbp ``game.actions`` nesting, and the
``boxScoreTraditional`` nested box. A payload whose rows are present but zero is
NOT coverage (mirrors ``observability.classify -> endpoint_absent``).

Read-only; stdlib only. Run from anywhere::

    python scripts/probe_v3_coverage.py [--root <store>] [--sample 20]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ROOT = Path("/mnt/sdv_repos/hoopR-nba-stats-raw/nba_stats/json")

FIRST_SEASON = 1996  # start-year label
LAST_SEASON = 2026

#: Endpoints whose season dir is keyed by the season END year (start + 1).
GAME_ENDPOINTS = ("playbyplayv3", "boxscoresummaryv2", "boxscoretraditionalv3")

#: Endpoints whose season dir is keyed by the season START year directly.
LEAGUE_ENDPOINTS = (
    "leaguestandingsv3",
    "leaguedashplayerstats",
    "leaguedashteamstats",
    "leaguedashlineups",
    "commonteamroster",
    "leaguegamelog",
    "drafthistory",  # 0 files today -- captured in Phase 3
)

ALL_ENDPOINTS = GAME_ENDPOINTS + LEAGUE_ENDPOINTS


def payload_rows(payload: object) -> int:
    """Max row count across the v3 payload shapes; 0 means an empty 200.

    * ``resultSets`` envelope -> max rowSet length across result sets.
    * pbp v3 ``game.actions`` -> number of actions.
    * ``boxScoreTraditional`` -> total players across home + away teams.
    """
    if not isinstance(payload, dict):
        return 0
    if "game" in payload and isinstance(payload["game"], dict):
        return len(payload["game"].get("actions") or [])
    box = payload.get("boxScoreTraditional")
    if isinstance(box, dict):
        total = 0
        for side in ("homeTeam", "awayTeam"):
            team = box.get(side)
            if isinstance(team, dict):
                total += len(team.get("players") or [])
        return total
    sets = payload.get("resultSets")
    if isinstance(sets, dict):  # singular resultSet shape
        sets = [sets]
    if isinstance(sets, list):
        return max(
            (len(s.get("rowSet") or []) for s in sets if isinstance(s, dict)), default=0
        )
    rs = payload.get("resultSet")
    if isinstance(rs, dict):
        return len(rs.get("rowSet") or [])
    return 0


def season_dir(root: Path, endpoint: str, season: int) -> Path:
    """Store directory for a start-year season, per the endpoint's keying."""
    dir_year = season + 1 if endpoint in GAME_ENDPOINTS else season
    return root / endpoint / str(dir_year)


@dataclass
class SeasonProbe:
    season: int
    dir_year: int
    files: int = 0
    sampled: int = 0
    populated: int = 0
    empty: int = 0

    @property
    def is_populated(self) -> bool:
        return self.populated > 0


@dataclass
class EndpointProbe:
    endpoint: str
    seasons: list[SeasonProbe] = field(default_factory=list)

    @property
    def floor(self) -> int | None:
        for sp in self.seasons:
            if sp.is_populated:
                return sp.season
        return None

    @property
    def total_files(self) -> int:
        return sum(sp.files for sp in self.seasons)


def probe_season(root: Path, endpoint: str, season: int, sample: int) -> SeasonProbe:
    d = season_dir(root, endpoint, season)
    sp = SeasonProbe(
        season=season, dir_year=season + 1 if endpoint in GAME_ENDPOINTS else season
    )
    if not d.is_dir():
        return sp
    files = sorted(d.glob("*.json"))
    sp.files = len(files)
    # Sample deterministically across the dir so a few empty leading files
    # don't mask a populated season (and vice versa).
    if sp.files <= sample:
        chosen = files
    else:
        step = sp.files / sample
        chosen = [files[int(i * step)] for i in range(sample)]
    for path in chosen:
        try:
            rows = payload_rows(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            sp.empty += 1
            continue
        sp.sampled += 1
        if rows > 0:
            sp.populated += 1
        else:
            sp.empty += 1
    return sp


def probe_endpoint(root: Path, endpoint: str, sample: int) -> EndpointProbe:
    ep = EndpointProbe(endpoint=endpoint)
    for season in range(FIRST_SEASON, LAST_SEASON + 1):
        ep.seasons.append(probe_season(root, endpoint, season, sample))
    return ep


def render_markdown(probes: list[EndpointProbe], root: Path, sample: int) -> str:
    lines: list[str] = []
    lines.append("# NBA v3 raw-store coverage probe")
    lines.append("")
    lines.append(f"- **Store root:** `{root}`")
    lines.append(f"- **Seasons:** {FIRST_SEASON}-{LAST_SEASON} (start-year labels)")
    lines.append(
        f"- **Sampling:** up to {sample} files per (endpoint, season) parsed for emptiness"
    )
    lines.append(
        "- **Populated** = a payload carrying > 0 rows (resultSets rowSet / "
        "pbp `game.actions` / `boxScoreTraditional` players). An empty 200 is not coverage."
    )
    lines.append("")
    lines.append(
        "Game endpoints (`playbyplayv3`, `boxscoresummaryv2`, `boxscoretraditionalv3`) "
        "are read from the **end-year** dir (`start + 1`); all others from the "
        "**start-year** dir. The `dir` column below states which directory was read."
    )
    lines.append("")

    # Floors summary -- the headline output.
    lines.append("## Season floors (feed `datasets.py` `season_floor`)")
    lines.append("")
    lines.append("| endpoint | dir keying | floor (start year) | total files |")
    lines.append("|---|---|---|---|")
    for ep in probes:
        keying = "end (start+1)" if ep.endpoint in GAME_ENDPOINTS else "start"
        floor = ep.floor
        floor_s = str(floor) if floor is not None else "**NONE (no populated season)**"
        lines.append(f"| `{ep.endpoint}` | {keying} | {floor_s} | {ep.total_files:,} |")
    lines.append("")

    # Per-endpoint per-season detail.
    for ep in probes:
        lines.append(f"## `{ep.endpoint}`")
        floor = ep.floor
        lines.append("")
        lines.append(
            f"- floor (start year): **{floor if floor is not None else 'NONE'}**"
        )
        lines.append(f"- total files: {ep.total_files:,}")
        lines.append("")
        lines.append("| season (start) | dir | files | sampled | populated | empty |")
        lines.append("|---|---|---|---|---|---|")
        for sp in ep.seasons:
            mark = ""
            if floor is not None and sp.season == floor:
                mark = " ◀ floor"
            lines.append(
                f"| {sp.season} | {sp.dir_year} | {sp.files} | {sp.sampled} | "
                f"{sp.populated} | {sp.empty} |{mark}"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"raw store json base (default: {DEFAULT_ROOT})",
    )
    ap.add_argument(
        "--sample",
        type=int,
        default=20,
        help="max files parsed per (endpoint, season) (default: 20)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the markdown report here instead of stdout",
    )
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        print(f"error: store root not found: {args.root}", file=sys.stderr)
        return 2

    probes = [probe_endpoint(args.root, ep, args.sample) for ep in ALL_ENDPOINTS]
    report = render_markdown(probes, args.root, args.sample)
    if args.out:
        args.out.write_text(report)
        print(f"wrote {args.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
