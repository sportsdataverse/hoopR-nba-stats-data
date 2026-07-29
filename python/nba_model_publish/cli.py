"""CLI entrypoint for nba_model_publish.

Usage::

    python -m nba_model_publish impact \\
        --seasons 1997:2026 \\
        --out out/impact \\
        [--lineup-source auto] \\
        [--cache-dir /data/nba_possessions] \\
        [--tag nba_player_impact] \\
        [--repo sportsdataverse/sportsdataverse-data] \\
        [--dry-run]

    python -m nba_model_publish upload \\
        --dir out/impact \\
        --tag nba_player_impact \\
        [--pattern "*.parquet"] \\
        [--repo sportsdataverse/sportsdataverse-data] \\
        [--dry-run]

``impact`` compiles each season's possessions (cached + resumable via the
per-game parquet cache), runs the impact model suite, writes one
``nba_player_impact_{season}.parquet`` per season plus a model-card sidecar,
and uploads the built seasons to the release tag. Requires live
stats.nba.com access (droplet + proxy host — cloud IPs hang).

``upload`` publishes an already-built directory without recomputing
anything; with ``--dry-run`` it is fully network-free (hermetic).
"""

from __future__ import annotations

import argparse
import os

from nba_data_build.publish import upload_artifacts

_REPO_DEFAULT = "sportsdataverse/sportsdataverse-data"

_IMPACT_RELEASE_NOTES = (
    "NBA player-impact model outputs (RAPM / adj-RAPM / SPM / BPM / DARKO / WAR; "
    "one parquet per season, one row per player-season-season_type (Regular "
    "Season + Playoffs; PlayIn excluded); stats.nba.com-sourced; Python-built "
    "by hoopR-nba-stats-data/python/nba_model_publish)."
)


def _parse_seasons(spec: str) -> list[int]:
    """Parse a ``"start:end"`` (inclusive) or single ``"year"`` season spec.

    Args:
        spec: Either ``"2022:2024"`` (inclusive range) or a single ``"2023"``.

    Returns:
        Ascending list of seasons.

    Raises:
        argparse.ArgumentTypeError: On malformed input or an inverted range.
    """
    try:
        if ":" in spec:
            lo_s, hi_s = spec.split(":", 1)
            lo, hi = int(lo_s), int(hi_s)
        else:
            lo = hi = int(spec)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid --seasons {spec!r}: expected 'YYYY' or 'YYYY:YYYY'") from exc
    if hi < lo:
        raise argparse.ArgumentTypeError(f"invalid --seasons {spec!r}: end {hi} precedes start {lo}")
    return list(range(lo, hi + 1))


SEASON_TYPES: tuple[str, ...] = ("Regular Season", "Playoffs")


def _parse_season_types(spec: str) -> list[str]:
    """Comma-separated stats.nba.com SeasonType strings -> validated list.

    Only "Regular Season" and "Playoffs" are supported. "PlayIn" is a real
    third SeasonType (2020+, ~4-6 games/yr) but is deliberately out of scope --
    see docs/superpowers/specs/2026-07-17-nba-player-impact-playoffs-design.md.

    Args:
        spec: e.g. ``"Regular Season,Playoffs"``.

    Returns:
        Season types in canonical build order (RS before PO).

    Raises:
        argparse.ArgumentTypeError: On an unknown or empty season type, or on
            "Playoffs" without "Regular Season" (see below).
    """
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("--season-types must not be empty")
    unknown = [p for p in parts if p not in SEASON_TYPES]
    if unknown:
        raise argparse.ArgumentTypeError(f"invalid --season-types {unknown!r}: expected any of {list(SEASON_TYPES)}")
    # canonical order: the PO pass reuses fitted values from the RS pass
    canonical = [t for t in SEASON_TYPES if t in parts]
    if "Playoffs" in canonical and "Regular Season" not in canonical:
        # A Playoffs pass structurally cannot run alone: it reuses the SPM
        # `coef` and `pts_per_win` fitted by the Regular Season pass in the
        # same invocation. Without RS, the builder hits a bare
        # `assert coef is not None` deep in the build -- and asserts vanish
        # under `python -O`, which would let coef=None reach nba_spm instead
        # of failing loudly. Reject this here, at parse time, where the
        # error is clear and unconditional.
        raise argparse.ArgumentTypeError(
            "--season-types 'Playoffs' requires 'Regular Season' in the same "
            "run: the Playoffs pass reuses the SPM coef and pts_per_win fitted "
            "by the Regular Season pass, so it cannot run alone. Pass "
            "'Regular Season,Playoffs' (or 'Regular Season' alone)."
        )
    return canonical


def _add_repo_dry(p: argparse.ArgumentParser) -> None:
    """Attach the shared ``--repo`` + ``--dry-run`` options to a subparser."""
    p.add_argument(
        "--repo",
        default=_REPO_DEFAULT,
        help="Target GitHub repository (owner/name).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Build/plan but do not upload.",
    )


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="nba_model_publish")
    sub = ap.add_subparsers(dest="cmd", required=True)

    imp = sub.add_parser(
        "impact",
        help="Build + upload per-season NBA player-impact tables (RAPM/adj-RAPM/SPM/BPM/DARKO/WAR).",
    )
    imp.add_argument(
        "--seasons",
        required=True,
        type=_parse_seasons,
        help="Season end-years, 2024 = 2023-24. Range 'YYYY:YYYY' (inclusive, "
        "e.g. '1997:2026') or a single 'YYYY'; seasons are built earliest-to-"
        "latest so multi-season priors flow forward.",
    )
    imp.add_argument(
        "--out",
        required=True,
        help="Output directory for nba_player_impact_{season}.parquet files.",
    )
    imp.add_argument(
        "--lineup-source",
        default="auto",
        help="Passed through to compile_nba_season (default 'auto').",
    )
    imp.add_argument(
        "--cache-dir",
        default=None,
        help="Possession per-game parquet cache directory "
        "(default: $SDV_PY_NBA_CACHE_DIR or ~/.sdv_py_nba_cache/possessions).",
    )
    imp.add_argument(
        "--delay-s",
        type=float,
        default=float(os.environ.get("SDV_NBA_DELAY_S", "0.6")),
        help="Sleep between live per-game fetches, seconds "
        "(default: $SDV_NBA_DELAY_S or 0.6). The stats.nba.com request budget "
        "(~250 req/10min) is SHARED with the R daily scraper -- use ~7 for an "
        "unattended multi-season backfill.",
    )
    imp.add_argument(
        "--season-types",
        type=_parse_season_types,
        default=list(SEASON_TYPES),
        help="Comma-separated season types to build "
        '(default: "Regular Season,Playoffs"). Rows are tagged with a '
        "season_type column. Pass 'Regular Season' alone to reproduce a "
        "regular-season-only build for diffing. PlayIn is not supported.",
    )
    imp.add_argument(
        "--replacement-level",
        type=float,
        default=-2.0,
        help="WAR replacement level, points per 100 possessions "
        "(default -2.0, the basketball-reference VORP convention).",
    )
    imp.add_argument(
        "--no-proxy",
        action="store_true",
        help="Fetch stats.nba.com DIRECTLY instead of through the ProxyBonanza pool. "
        "Only correct from a residential IP -- stats.nba.com HANGS (does not error) on "
        "datacenter/cloud IPs, so an unattended/droplet run without a proxy will stall, "
        "not fail loudly. Default: rotate through the pool (PROXY_ENDPOINT/_KEY/_PKG).",
    )
    imp.add_argument(
        "--raw-store-dir",
        default=os.environ.get("SDV_PY_NBA_RAW_JSON_DIR"),
        metavar="DIR_OR_URL",
        help="Read committed hoopR-nba-stats-raw JSON instead of the live API: a local "
        "nba_stats/json checkout OR an http(s):// base such as "
        "https://raw.githubusercontent.com/sportsdataverse/hoopR-nba-stats-raw/main/nba_stats/json "
        "(or a CDN mirror). Removes the ~1GB clone and serves every season-level "
        "surface from the committed tree -- per-game payloads, game discovery, "
        "playerindex, biostats, and both the team and player leaguegamelog captures "
        "-- so a cloud runner needs no proxy for a season already in the store. "
        "Defaults to $SDV_PY_NBA_RAW_JSON_DIR.",
    )
    imp.add_argument("--tag", default="nba_player_impact", help="GitHub release tag.")
    _add_repo_dry(imp)

    up = sub.add_parser(
        "upload",
        help="Upload an already-built artifact directory to a release (no recompute; --dry-run is fully network-free).",
    )
    up.add_argument(
        "--dir",
        required=True,
        dest="artifacts_dir",
        help="Directory containing the built artifacts.",
    )
    up.add_argument("--tag", required=True, help="GitHub release tag.")
    up.add_argument(
        "--pattern",
        default="*.parquet",
        help="Glob (relative to --dir) selecting the assets to upload.",
    )
    _add_repo_dry(up)

    return ap


def _print_result(res: dict, repo: str, tag: str, dry_run: bool) -> None:
    suffix = " (dry-run)" if dry_run else ""
    failed = res.get("failed") or []
    failed_part = f" failed={len(failed)}" if failed else ""
    print(f"publish: uploaded={res['uploaded']} files={len(res['files'])}{failed_part} -> {repo}:{tag}{suffix}")


def _resolve_proxy_provider(no_proxy: bool, raw_store_dir: str | None = None):
    """Build the rotating proxy provider, or ``None`` for a direct (residential) run.

    Proxy is the DEFAULT: stats.nba.com hangs rather than errors on datacenter IPs,
    so an unattended run that silently forgot its proxy would stall for hours instead
    of failing. Refusing to start beats hanging. ``--no-proxy`` is the explicit opt-out.

    A configured ``raw_store_dir`` is the other opt-out, and the one CI uses. The
    store answers the fetches, so demanding proxy credentials up front would abort
    exactly the runs this exists to enable -- a GitHub Actions build with the
    committed captures and no ``PROXY_*`` secrets. Missing proxies therefore warn
    instead of exiting; a genuine store miss still needs the network, so the
    warning says so rather than implying the run is guaranteed offline.
    """
    if no_proxy:
        print("impact: --no-proxy -- fetching stats.nba.com directly (residential IP only)")
        return None

    from nba_data_build.scrape.proxy import RoundRobin, load_proxies

    proxies = load_proxies()
    if not proxies and raw_store_dir:
        print(
            "impact: no proxies configured -- proceeding because --raw-store-dir is set, "
            "so the committed captures serve the fetches. A season MISSING from the store "
            "would fall through to stats.nba.com unproxied and hang on a datacenter IP."
        )
        return None
    if not proxies:
        raise SystemExit(
            "impact: no proxies available (PROXY_ENDPOINT / PROXY_KEY / PROXY_PKG unset "
            "or the vendor API is unreachable). stats.nba.com HANGS on datacenter IPs, so "
            "this would stall rather than fail. Set the proxy env vars, pass --raw-store-dir "
            "to serve the fetches from committed captures, or pass --no-proxy "
            "if you are on a residential IP."
        )
    print(f"impact: rotating through {len(proxies)} proxies")
    return RoundRobin(proxies).next


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "impact":
        from .builders import build_nba_player_impact

        built = build_nba_player_impact(
            args.seasons,
            args.out,
            proxy_provider=_resolve_proxy_provider(args.no_proxy, args.raw_store_dir),
            lineup_source=args.lineup_source,
            cache_dir=args.cache_dir,
            delay_s=args.delay_s,
            season_types=args.season_types,
            replacement_level=args.replacement_level,
            raw_store_dir=args.raw_store_dir,
        )
        total_rows = sum(b["rows"] for b in built)
        res = upload_artifacts(
            args.out,
            args.tag,
            args.repo,
            seasons=[b["season"] for b in built],
            # all three formats ship to the tag (2026-07 decision; was
            # parquet-only at launch)
            exts=("parquet", "rds", "csv"),
            notes=_IMPACT_RELEASE_NOTES,
            dry_run=args.dry_run,
        )
        card_res = upload_artifacts(
            args.out,
            args.tag,
            args.repo,
            pattern="*_card.json",
            notes=_IMPACT_RELEASE_NOTES,
            dry_run=args.dry_run,
        )
        suffix = " (dry-run)" if args.dry_run else ""
        failed = list(res.get("failed") or []) + list(card_res.get("failed") or [])
        failed_part = f" failed={len(failed)}" if failed else ""
        print(
            f"publish: seasons={len(built)} rows={total_rows} "
            f"uploaded={res['uploaded'] + card_res['uploaded']} "
            f"files={len(res['files']) + len(card_res['files'])}"
            f"{failed_part} -> {args.repo}:{args.tag}{suffix}"
        )
    elif args.cmd == "upload":
        res = upload_artifacts(
            args.artifacts_dir,
            args.tag,
            args.repo,
            pattern=args.pattern,
            dry_run=args.dry_run,
        )
        _print_result(res, args.repo, args.tag, args.dry_run)
    return 0
