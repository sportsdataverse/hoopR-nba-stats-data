"""Generate the per-dataset documentation (spec D40/D43).

Answers, for every dataset: **what builds it, where it is published, what is in
it, and when it last ran.** Hand-written docs go stale the first time a column
is added, so these are generated and drift-gated -- adding a dataset or a
column without regenerating is a red build.

Sources, all of them existing:

* ``nba_data_build.reshape.datasets.DATASETS`` -- dataset, output stem, tag
* ``nba_data_build.models``                    -- column names and types
* ``column_descriptions.yaml`` (this package)  -- authored for this league
* ``nba_stats/nba_stats_games_in_data_repo.parquet`` -- per-season game counts
* ``gh release view``                          -- last published (opt-in)

Descriptions are authored for THIS league and live in this package, never read
from a sibling checkout (CI has none) and never borrowed from another sport's
schema store -- a borrowed description is an invented one (the WBB pilot's
borrowed store produced `assists` = "Assisted tackles"). A column with no
entry gets an empty cell, because an empty cell is an honest TODO and an
invented sentence is worse than nothing.

The D2 note: this repo's single build engine is the registry-driven reshape
CLI (``python -m nba_data_build.reshape``); the numbered
``python/nba_stats_NN_*_creation.py`` entrypoints are thin per-dataset shims
over it, so BUILDER below maps each dataset to its shim.

Example:
    Regenerate everything::

        uv run python -m nba_data_build.docs

    Fail if anything is stale (CI)::

        uv run python -m nba_data_build.docs --check --no-live
"""

from __future__ import annotations

import argparse
import json
import subprocess
from functools import lru_cache
from pathlib import Path

import polars as pl

from nba_data_build.models import MODELS, polars_schema
from nba_data_build.reshape.datasets import BY_KEY, DATASETS

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs" / "datasets"
RELEASE_REPO = "sportsdataverse/sportsdataverse-data"
RELEASE_URL = f"https://github.com/{RELEASE_REPO}/releases/tag"

BEGIN = "<!-- BEGIN GENERATED: datasets -->"
END = "<!-- END GENERATED: datasets -->"

#: dataset key -> the numbered shim that builds it (intended build order).
BUILDER = {
    "standings": "python/nba_stats_01_standings_creation.py",
    "player_season_stats": "python/nba_stats_02_player_season_stats_creation.py",
    "team_season_stats": "python/nba_stats_03_team_season_stats_creation.py",
    "lineups": "python/nba_stats_04_lineups_creation.py",
    "rosters": "python/nba_stats_05_rosters_creation.py",
    "coaches": "python/nba_stats_06_coaches_creation.py",
    "draft": "python/nba_stats_07_draft_creation.py",
    "schedules": "python/nba_stats_08_schedules_creation.py",
    "player_game_logs": "python/nba_stats_09_player_game_logs_creation.py",
    "pbp": "python/nba_stats_10_pbp_creation.py",
    "game_rosters": "python/nba_stats_11_game_rosters_creation.py",
    "officials": "python/nba_stats_12_officials_creation.py",
    "player_boxscores": "python/nba_stats_13_player_boxscores_creation.py",
    "team_boxscores": "python/nba_stats_14_team_boxscores_creation.py",
    "shots": "python/nba_stats_15_shots_creation.py",
    "game_matchups": "python/nba_stats_16_game_matchups_creation.py",
    "schedule_master": "python/nba_stats_99_schedule_master_creation.py",
    "games_in_data_repo": "python/nba_stats_99_schedule_master_creation.py",
}

#: The stage-99 schedule-master artifacts (spec D34/D36): committed to this
#: repo rather than released per-season. Both come out of one pass over the
#: committed per-season schedule files, so they cannot drift from each other.
MASTERS = {
    "schedule_master": "nba_stats/nba_stats_schedule_master.parquet",
    "games_in_data_repo": "nba_stats/nba_stats_games_in_data_repo.parquet",
}

#: Every documented page: the 16 registry datasets + the 2 master artifacts.
PAGES: tuple[str, ...] = tuple(d.key for d in DATASETS) + tuple(MASTERS)

AUTOMATION = (
    "`.github/workflows/daily_nba_stats.yml` — nightly scrape + reshape + "
    "publish. Runs `scripts/daily_nba_stats_python_processor.sh`; the "
    "stage-99 schedule master is restamped at the end of every run."
)


@lru_cache(maxsize=1)
def _descriptions() -> dict[str, str]:
    """Column name -> description, flattened across the store.

    A column named ``game_id`` means the same thing in every dataset that
    carries it, so the store is keyed by column NAME.
    """
    path = Path(__file__).with_name("column_descriptions.yaml")
    if not path.exists():
        return {}
    import yaml

    store = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        name: text.strip() for name, text in store.items() if isinstance(text, str) and text.strip()
    }


@lru_cache(maxsize=1)
def _games_in_repo() -> pl.DataFrame | None:
    path = REPO_ROOT / MASTERS["games_in_data_repo"]
    if not path.exists():
        return None
    try:
        return pl.read_parquet(path)
    except Exception:
        return None


def release_status(tag: str | None, *, live: bool) -> dict[str, str]:
    """Last-published info for a release tag. Empty when offline or missing."""
    if not live or tag is None:
        return {}
    try:
        out = subprocess.run(
            ["gh", "release", "view", tag, "--repo", RELEASE_REPO, "--json", "publishedAt,assets"],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if out.returncode != 0:
            return {}
        data = json.loads(out.stdout)
        assets = data.get("assets") or []
        # `publishedAt` is when the TAG was created, which for a rolling
        # release is stale; the newest asset timestamp is the honest value.
        updated = max((a.get("updatedAt") or "" for a in assets), default="")
        return {
            "published": updated[:10],
            "created": (data.get("publishedAt") or "")[:10],
            "assets": str(len(assets)),
        }
    except Exception:
        return {}


def column_table(dataset: str) -> str:
    """The ``col_name | type | description`` table for one dataset."""
    if dataset not in MODELS:
        return "_No published asset to derive a schema from yet; no model._\n"
    descriptions = _descriptions()
    lines = ["| col_name | type | description |", "|---|---|---|"]
    for name, dtype in polars_schema(dataset).items():
        lines.append(f"| `{name}` | {dtype} | {descriptions.get(name, '')} |")
    return "\n".join(lines) + "\n"


#: Standing facts a per-season count table cannot say for itself, appended under
#: `## Coverage`. Authored here rather than in the generated page so a regen
#: cannot drop them; static text, so the drift gate compares them like any other
#: structure. Keep them short and link the detail -- the full accounting lives in
#: `docs/nba-v3-coverage.md`, not copied into every page.
COVERAGE_NOTES: dict[str, str] = {
    "pbp": """
**Every NBA season type is published** — preseason (`001`), regular season
(`002`), All-Star (`003`), playoffs (`004`), play-in (`005`) and NBA Cup final
(`006`) — so `games known` counts the full game universe, and a season's
`games built` is below it wherever upstream published no play-by-play.

**Preseason play-by-play begins with the 2010-11 season** (END-year 2011): 0 of
119 preseason games in END-year 2010, 119 of 119 in 2011. That era boundary is
1,567 of the 1,602 scheduled games without play-by-play; the rest are All-Star
exhibitions and never-played dates.

**These are upstream absences, not capture gaps — do not re-scrape them.** Each
was re-probed live (2026-08-12/13): stats.nba.com returns a valid `playbyplayv3`
payload with `actions: []` on the same session that returns 500+ actions for
other games. [`docs/nba-v3-coverage.md`](../nba-v3-coverage.md) is the canonical
accounting — per-type counts, the individual game ids, and the `games_no_pbp` vs
`games_failed` distinction.
""",
}


def coverage_table(dataset: str) -> str:
    """The per-season counts plus any standing coverage note for *dataset*."""
    return _coverage_counts(dataset) + COVERAGE_NOTES.get(dataset, "")


def _coverage_counts(dataset: str) -> str:
    """Per-season game counts for game-level datasets, from the manifest."""
    games = _games_in_repo()
    if dataset in MASTERS:
        if games is None:
            return "_No committed manifest in this checkout._\n"
        seasons = games["season"].n_unique()
        return f"_{games.height:,} games across {seasons} seasons (committed)._\n"
    spec = BY_KEY[dataset]
    flag = f"in_{dataset}"
    if spec.level != "game" or games is None or flag not in games.columns:
        return (
            f"_Coverage is tracked per release asset on "
            f"[`{spec.release_tag}`]({RELEASE_URL}/{spec.release_tag})._\n"
        )
    counts = (
        games.group_by("season")
        .agg(pl.col(flag).sum().alias("games"), pl.len().alias("of"))
        .sort("season")
    )
    lines = ["| season | games built | games known |", "|---:|---:|---:|"]
    for row in counts.to_dicts():
        lines.append(f"| {row['season']} | {row['games']:,} | {row['of']:,} |")
    return "\n".join(lines) + "\n"


def _seasons_built(dataset: str) -> str:
    games = _games_in_repo()
    flag = f"in_{dataset}"
    if games is None or flag not in games.columns:
        return ""
    seasons = games.filter(pl.col(flag) == True)["season"].unique().sort()  # noqa: E712
    if seasons.is_empty():
        return ""
    count = len(seasons)
    if count == 1:
        return f"{seasons[0]} (1 season)"
    # Seasons are strings ("2023-24" span form here); contiguity is judged on
    # the leading start year so a sparse range is labelled as such rather than
    # implying completeness that isn't there.
    years = sorted(int(str(s)[:4]) for s in seasons)
    contiguous = count == years[-1] - years[0] + 1
    span = f"{seasons[0]}–{seasons[-1]} ({count} seasons"
    return span + (")" if contiguous else ", non-contiguous)")


def dataset_page(dataset: str, *, live: bool) -> str:
    if dataset in MASTERS:
        return _master_page(dataset)
    spec = BY_KEY[dataset]
    status = release_status(spec.release_tag, live=live)
    seasons = _seasons_built(dataset)

    return f"""# `{dataset}`

{spec.nba_type} — `{spec.endpoint or "derived"}` ({spec.level}-level).

| | |
|---|---|
| **Builder** | [`{BUILDER[dataset]}`]({"../../" + BUILDER[dataset]}) |
| **Release tag** | [`{spec.release_tag}`]({RELEASE_URL}/{spec.release_tag}) |
| **File stem** | `{spec.stem}_{{season}}.{{parquet,csv,rds}}` |
| **Seasons built** | {seasons or "—"} |
| **Last published** | {status.get("published") or "—"} (newest release asset) |
| **Tag created** | {status.get("created") or "—"} |
| **Release assets** | {status.get("assets") or "—"} |

## Automation

{AUTOMATION}

## Columns

{column_table(dataset)}
## Coverage

{coverage_table(dataset)}"""


def _master_page(dataset: str) -> str:
    return f"""# `{dataset}`

Stage-99 schedule-master artifact (spec D34/D36): {"every game the schedule knows about — the denominator" if dataset == "schedule_master" else "only games present in at least one compilation — the numerator, what consumers join against"}. The ``in_*`` flag set is derived from the dataset registry, never hand-listed.

| | |
|---|---|
| **Builder** | [`{BUILDER[dataset]}`]({"../../" + BUILDER[dataset]}) |
| **Committed at** | `{MASTERS[dataset]}` |

## Automation

{AUTOMATION}

## Columns

{column_table(dataset)}
## Coverage

{coverage_table(dataset)}"""


def summary_table(*, live: bool) -> str:
    """The block embedded in README.md and CLAUDE.md."""
    lines = [
        "| Script | Dataset | Release tag | Last published |",
        "|---|---|---|---|",
    ]
    for dataset in sorted(PAGES, key=lambda k: BUILDER[k]):
        builder = BUILDER[dataset]
        if dataset in MASTERS:
            where = f"`{MASTERS[dataset]}` (committed)"
            published = "—"
        else:
            spec = BY_KEY[dataset]
            status = release_status(spec.release_tag, live=live)
            where = f"[`{spec.release_tag}`]({RELEASE_URL}/{spec.release_tag})"
            published = status.get("published", "—")
        lines.append(
            f"| [`{builder}`]({builder}) "
            f"| [`{dataset}`](docs/datasets/{dataset}.md) "
            f"| {where} "
            f"| {published} |"
        )
    return "\n".join(lines)


#: Lines whose values move on every publish/data commit; the drift gate
#: ignores them so a daily run cannot red an unrelated PR.
_VOLATILE = ("**Last published**", "**Tag created**", "**Release assets**", "**Seasons built**")


def _without_status(text: str) -> str:
    """Strip publish-status and coverage values; compare structure only.

    Coverage derives from the committed master parquet, which the daily build
    restamps -- and which CI's sparse checkout may not even have. Structure
    and columns are what the gate is for.
    """
    kept: list[str] = []
    in_coverage = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_coverage = line.startswith("## Coverage")
        if in_coverage and (line.startswith("|") or line.startswith("_")):
            continue
        if any(marker in line for marker in _VOLATILE):
            continue
        # The summary table's trailing "| <date> |" column moves too; drop it.
        if line.startswith("| [`") and line.count("|") >= 5:
            line = "|".join(line.split("|")[:-2]) + "|"
        kept.append(line)
    return "\n".join(kept)


def _replace_block(text: str, block: str) -> str:
    if BEGIN not in text or END not in text:
        return text.rstrip() + f"\n\n## Datasets\n\n{BEGIN}\n{block}\n{END}\n"
    head, _, rest = text.partition(BEGIN)
    _, _, tail = rest.partition(END)
    return f"{head}{BEGIN}\n{block}\n{END}{tail}"


def generate(*, check: bool = False, live: bool = True) -> int:
    """Write (or verify) every generated doc. Returns 0 when in sync."""
    stale: list[str] = []
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    wanted: dict[Path, str] = {DOCS_DIR / f"{d}.md": dataset_page(d, live=live) for d in PAGES}
    block = summary_table(live=live)
    for name in ("README.md", "CLAUDE.md"):
        path = REPO_ROOT / name
        if path.exists():
            wanted[path] = _replace_block(path.read_text(encoding="utf-8"), block)

    for path, content in wanted.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == content:
            continue
        if check:
            if current is not None and _without_status(current) == _without_status(content):
                continue
            stale.append(str(path.relative_to(REPO_ROOT)))
        else:
            path.write_text(content, encoding="utf-8", newline="")

    if check and stale:
        print("::error ::generated docs are stale; run `uv run python -m nba_data_build.docs`")
        for item in stale:
            print(f"  {item}")
        return 1
    if not check:
        print(f"wrote {len(wanted)} generated file(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate per-dataset documentation.")
    parser.add_argument("--check", action="store_true", help="Fail if anything is stale")
    parser.add_argument(
        "--no-live",
        action="store_true",
        help="Skip `gh release view` (offline; status columns render as em dashes)",
    )
    args = parser.parse_args(argv)
    return generate(check=args.check, live=not args.no_live)


if __name__ == "__main__":
    raise SystemExit(main())
