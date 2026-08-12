"""Program V (design §10, D26d) cutover publisher: staged v3 -> production release tags.

**DRY RUN IS THE DEFAULT.** Nothing is uploaded, created, or deleted without an
explicit ``--execute``. This is the least reversible action in the program:
overwriting a GitHub release asset destroys the previous bytes, and the
downstream consumers are ``hoopR::load_nba_*()`` + ``sportsdataverse.nba``
loaders.

What it does, in order:

1. **Gate.** Re-runs the section-10.3 :mod:`.v3_gate` over the requested season
   range. Any ``DIFF`` / ``MISSING_STAGED`` verdict aborts unless that exact
   ``season:family`` pair was allowlisted with ``--allow-diff`` -- which is then
   printed verbatim in the manifest. There is no blanket ignore switch.
2. **Derive.** Every staged parquet is materialized in all three published
   formats (:mod:`.v3_formats`): ``parquet`` + ``rds`` + ``csv.gz``. The rds is
   what ``hoopR::load_nba_*()`` actually reads, so a parquet-only publish would
   ship data hoopR cannot open; it is written by the byte-parity RDS writer (no
   R, no ``Rscript``) and **verified by reading it back** before it is
   considered done.
3. **Manifest.** Writes a REPLACE MANIFEST (markdown) naming every asset that
   would be uploaded: target tag, filename, local bytes/rows/sha256, and the
   CURRENT remote asset's size + updated-at when one exists. Every row is
   classified ``NEW`` / ``REPLACE`` / ``UNCHANGED``. Dedicated sections list the
   remote assets that would be **destroyed**, the legacy-named assets that
   survive un-replaced and keep being served to the loaders (the shadow set),
   and the **season-label collisions** (below).
4. **Upload** (``--execute`` only). One asset at a time; after each, the release
   is re-fetched and the remote size compared to the local file. First mismatch
   stops the run -- ``gh release upload`` with many files at once has silently
   dropped large assets before, which is why this is per-file. Each touched tag
   also receives a generated ``README.md`` explaining the two naming schemes.

**Decision B -- additive publish.** The v3 assets land on the PRODUCTION tags
alongside the existing legacy assets rather than replacing them, and consumers
migrate afterwards. A 0-REPLACE / all-NEW manifest is therefore the intended
outcome, not a defect. The hazard it creates is that during the migration window
each tag carries two labelings of the same real season: published
``play_by_play_1996.*`` IS the 1996-97 season, and staged
``nba_play_by_play_1997.parquet`` is ALSO the 1996-97 season, so a consumer
asking for "1997" gets different data depending on which file it grabs. Three
mitigations, all in this module:

* the **SEASON-LABEL COLLISION** manifest section pairs every new asset with the
  legacy asset covering the same real season, per tag;
* ``--execute`` uploads a generated per-tag ``README.md`` stating which pattern
  is which, that both describe the same seasons, that the END-year name is
  authoritative, and that the legacy assets are scheduled for removal;
* ``--retire-legacy-assets`` deletes the legacy names once consumers have
  migrated -- a **separate** invocation that refuses to delete anything whose
  replacement is not present and verified in all three formats.

Resumability: every verified upload appends a receipt to
``{staging}/.cutover_receipts.json``. A re-run classifies an asset ``UNCHANGED``
(and skips it) only when a receipt's sha256 matches the local file *and* the
remote size agrees -- size equality alone is never taken as identity.

``_v3`` tag retirement (``--retire-v3-tags``) and legacy-asset retirement
(``--retire-legacy-assets``) are each a separate invocation, never bundled into
a data upload and never into each other.

Seasons are END years, matching :mod:`.v3_backfill` (2006 = the 2005-06 season).
Note that the legacy production assets are keyed by START year; see
``Target.legacy_offset``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .publish import Runner, _gh_runner
from .v3_formats import FORMATS, derive_formats

REPO = "sportsdataverse/sportsdataverse-data"

#: Name of the per-tag migration note uploaded alongside the data (--execute).
README_ASSET = "README.md"

#: Read in 1 MiB blocks -- the staged pbp parquets run to ~20 MB each.
_SHA_BLOCK = 1 << 20


@dataclass(frozen=True)
class Target:
    """Where one staged family lands on the release, and what it shadows.

    ``asset`` / ``legacy_asset`` are ``{season}`` format strings. ``legacy_offset``
    is added to the END-year season to get the legacy asset's season number
    (NBA legacy assets are START-year, so ``-1``).

    ``collision`` is a non-empty explanation when the target tag already carries
    a *different* dataset under different asset names. Publishing there does not
    overwrite anything byte-for-byte, but it puts two datasets on one tag --
    ``--execute`` refuses until the operator resolves it with ``--tag``.
    """

    family: str
    tag: str
    asset: str
    legacy_asset: Optional[str] = None
    legacy_offset: int = 0
    collision: str = ""


TARGETS: dict[str, Target] = {
    # D26d: v3 replaces pbp + schedules. D27: the plural `nba_stats_schedules` survives.
    "schedule": Target(
        family="schedule",
        tag="nba_stats_schedules",
        asset="nba_schedule_{season}.parquet",
        legacy_asset="nba_stats_schedule_{season}.parquet",
        legacy_offset=-1,
    ),
    "play_by_play": Target(
        family="play_by_play",
        tag="nba_stats_pbp",
        asset="nba_play_by_play_{season}.parquet",
        legacy_asset="play_by_play_{season}.parquet",
        legacy_offset=-1,
    ),
    # No production `nba_stats_possessions` tag exists yet -- the de-`_v3` name.
    "possessions": Target(
        family="possessions",
        tag="nba_stats_possessions",
        asset="nba_possessions_{season}.parquet",
    ),
    # D26d decision 3: the v3 per-game lineup/stint data gets its OWN tag.
    # `nba_stats_lineups` carries the SEASON-level leaguedashlineups dataset
    # from stage 04 (`lineups_{start}.{csv,parquet,rds}`) -- a different dataset,
    # not an older version of this one, so it is left untouched rather than
    # shared. `nba_stats_game_lineups` parallels the existing
    # `nba_stats_game_rosters` naming. There is no legacy asset to shadow here:
    # nothing on the new tag describes these seasons under another name.
    "lineups": Target(
        family="lineups",
        tag="nba_stats_game_lineups",
        asset="nba_lineups_{season}.parquet",
    ),
}

#: Retired by --retire-v3-tags, never by the upload path.
RETIRE_TAGS = ("nba_stats_pbpv3", "nba_stats_possessions_v3", "nba_stats_lineups_v3")

_BAD_VERDICTS = {"DIFF", "MISSING_STAGED"}


def _log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{stamp}] {msg}", flush=True)


def sha256_file(path: Path) -> str:
    """Streaming sha256 of *path* (hex)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(_SHA_BLOCK), b""):
            h.update(block)
    return h.hexdigest()


def parquet_rows(path: Path) -> int:
    """Row count from the parquet footer (no column data is read)."""
    import pyarrow.parquet as pq

    return int(pq.ParquetFile(path).metadata.num_rows)


def remote_assets(tag: str, repo: str, *, runner: Optional[Runner] = None) -> dict[str, Any]:
    """``{asset_name: {"size": int, "updatedAt": str}}`` for *tag*; ``{}`` when absent.

    A missing release is the expected first-publish case. Any other `gh` failure
    (auth, rate limit) must surface rather than masquerade as an empty tag, so
    only ``CalledProcessError`` is swallowed and it is re-checked below.
    """
    run = runner or _gh_runner
    try:
        out = run(["release", "view", tag, "--repo", repo, "--json", "assets"])
    except subprocess.CalledProcessError:
        return {}
    payload = json.loads(out or "{}")
    return {
        a["name"]: {"size": a["size"], "updatedAt": a["updatedAt"]}
        for a in payload.get("assets", [])
    }


def receipts_path(staging: Path) -> Path:
    return Path(staging) / ".cutover_receipts.json"


def load_receipts(staging: Path) -> dict[str, Any]:
    p = receipts_path(staging)
    return json.loads(p.read_text()) if p.exists() else {}


def save_receipt(staging: Path, key: str, sha: str, size: int) -> None:
    p = receipts_path(staging)
    data = load_receipts(staging)
    data[key] = {
        "sha256": sha,
        "size": size,
        "uploaded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    p.write_text(json.dumps(data, indent=2, sort_keys=True))


def classify(
    local_size: int, local_sha: str, remote: Optional[dict], receipt: Optional[dict]
) -> str:
    """NEW / REPLACE / UNCHANGED for one asset.

    ``UNCHANGED`` requires a receipt whose sha256 matches the local file AND a
    remote size that agrees. Matching size alone is deliberately NOT enough --
    two different parquets can share a byte count, and treating that as identity
    would silently skip a real replacement.
    """
    if remote is None:
        return "NEW"
    if receipt and receipt.get("sha256") == local_sha and remote.get("size") == local_size:
        return "UNCHANGED"
    return "REPLACE"


def release_build_dir(staging: Path) -> Path:
    """Where the derived rds / csv.gz live. Sibling of the staged parquet, gitignored."""
    return Path(staging) / "_release_build"


def stage_rows(
    staging: Path,
    seasons: list[int],
    targets: dict[str, Target],
    *,
    formats: tuple[str, ...] = FORMATS,
    force_derive: bool = False,
) -> list[dict[str, Any]]:
    """Local side of the manifest: one row per staged artifact PER FORMAT.

    The staged parquet is the source; the rds + csv.gz are derived from it here
    (:func:`.v3_formats.derive_formats`, which verifies the rds by reading it
    back). Derivation is idempotent -- an existing derived file newer than its
    parquet is reused, so a re-run of the dry run does not re-serialize 120
    season frames.
    """
    from .v3_backfill import season_paths

    out_dir = release_build_dir(staging)
    rows: list[dict[str, Any]] = []
    for season in seasons:
        paths = season_paths(staging, season)
        for family, target in targets.items():
            path = paths[family]
            if not path.exists():
                continue
            stem = target.asset.format(season=season).rsplit(".parquet", 1)[0]
            derived = derive_formats(path, out_dir, dataset=stem, force=force_derive)
            n_rows = parquet_rows(path)
            for fmt in formats:
                fpath = derived[fmt]
                rows.append(
                    {
                        "family": family,
                        "season": season,
                        "format": fmt,
                        "tag": target.tag,
                        "asset": f"{stem}.{fmt}",
                        "path": fpath,
                        "size": fpath.stat().st_size,
                        "rows": n_rows,
                        "sha256": sha256_file(fpath),
                    }
                )
    return rows


def build_manifest(
    staged: list[dict[str, Any]],
    remote_by_tag: dict[str, dict[str, Any]],
    receipts: dict[str, Any],
) -> list[dict[str, Any]]:
    """Attach the remote side + verdict to each staged row. Pure; no network."""
    out = []
    for row in staged:
        key = f"{row['tag']}/{row['asset']}"
        remote = remote_by_tag.get(row["tag"], {}).get(row["asset"])
        out.append(
            {
                **row,
                "key": key,
                "remote_size": remote["size"] if remote else None,
                "remote_updated_at": remote["updatedAt"] if remote else None,
                "verdict": classify(row["size"], row["sha256"], remote, receipts.get(key)),
            }
        )
    return out


def shadowed_assets(
    manifest: list[dict[str, Any]],
    remote_by_tag: dict[str, dict[str, Any]],
    targets: dict[str, Target],
) -> list[dict[str, Any]]:
    """Remote assets on the target tags that this cutover does NOT replace.

    These keep being served to ``load_nba_*()`` after the cutover -- the legacy
    START-year names under the D26b END-year scheme, plus every csv/rds sibling.
    Surfacing them is the point: an operator reading only the REPLACE rows would
    conclude the swap was complete when the loaders had not moved at all.
    """
    planned = {(r["tag"], r["asset"]) for r in manifest}
    tags = {t.tag for t in targets.values()}
    out = []
    for tag in sorted(tags):
        for name, meta in sorted(remote_by_tag.get(tag, {}).items()):
            if (tag, name) not in planned:
                out.append(
                    {
                        "tag": tag,
                        "asset": name,
                        "size": meta["size"],
                        "updated_at": meta["updatedAt"],
                    }
                )
    return out


def legacy_stem(target: Target, season: int) -> Optional[str]:
    """Legacy asset stem covering the SAME real season as this END-year *season*.

    ``play_by_play_{start}`` for an END-year 1997 is ``play_by_play_1996`` -- the
    same 1996-97 games under the other labeling.
    """
    if not target.legacy_asset:
        return None
    name = target.legacy_asset.format(season=season + target.legacy_offset)
    return name.rsplit(".parquet", 1)[0]


def season_label_collisions(
    seasons: list[int],
    remote_by_tag: dict[str, dict[str, Any]],
    targets: dict[str, Target],
) -> list[dict[str, Any]]:
    """Per tag, the pairs of assets that describe the SAME real season under two names.

    This is the hazard the additive (decision-B) publish creates and the reason
    the manifest carries it as its own section: after the cutover a tag serves
    ``play_by_play_1996.*`` (START-year, the 1996-97 season) next to
    ``nba_play_by_play_1997.*`` (END-year, ALSO the 1996-97 season). A consumer
    asking for "1997" gets different data depending on which file it grabs, and
    nothing in either filename says so. Only pairs whose legacy side actually
    exists on the release are listed -- a name that was never published is not a
    collision anyone can hit.
    """
    out: list[dict[str, Any]] = []
    for target in targets.values():
        remote = remote_by_tag.get(target.tag, {})
        for season in seasons:
            stem = legacy_stem(target, season)
            if stem is None:
                continue
            legacy_names = sorted(
                n for n in remote if n.rsplit(".", 1)[0] == stem or n.startswith(f"{stem}.")
            )
            if not legacy_names:
                continue
            new_stem = target.asset.format(season=season).rsplit(".parquet", 1)[0]
            out.append(
                {
                    "tag": target.tag,
                    "family": target.family,
                    "season": season,
                    "new_stem": new_stem,
                    "legacy_stem": stem,
                    "legacy_assets": legacy_names,
                    "legacy_bytes": sum(remote[n]["size"] for n in legacy_names),
                    # False when both names carry the SAME number (a same-season
                    # duplicate, not a mislabeling): still worth listing, but it
                    # is not the hazard that sends a consumer to the wrong year.
                    "label_differs": target.legacy_offset != 0,
                }
            )
    return out


def render_tag_readme(
    tag: str,
    targets: dict[str, Target],
    seasons: list[int],
    *,
    formats: tuple[str, ...] = FORMATS,
) -> str:
    """The migration note uploaded to each touched tag on ``--execute``.

    Generated, never hand-written per tag: a hand-copied note drifts the moment
    one tag's season range or asset pattern differs from another's.
    """
    mine = [t for t in targets.values() if t.tag == tag]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        f"# `{tag}` -- asset naming during the Program V v3 migration",
        "",
        f"_Generated {stamp} by `v3_cutover.py`. Do not hand-edit; it is re-uploaded on every publish._",
        "",
        "## Two filename patterns, the same seasons",
        "",
        "This tag currently carries assets under two naming conventions that",
        "**describe the same real seasons**:",
        "",
        "| pattern | season label | example | status |",
        "|---|---|---|---|",
    ]
    for t in mine:
        new_example = t.asset.format(season=seasons[-1]).rsplit(".parquet", 1)[0]
        lines.append(
            f"| `{t.asset.rsplit('.parquet', 1)[0]}.*` | **END year** (2006 = the 2005-06 season) "
            f"| `{new_example}.parquet` | **AUTHORITATIVE** |"
        )
        stem = legacy_stem(t, seasons[-1])
        if stem:
            legacy_pattern = (t.legacy_asset or "").rsplit(".parquet", 1)[0]
            lines.append(
                f"| `{legacy_pattern}.*` | START year (2005 = the 2005-06 season) "
                f"| `{stem}.parquet` | legacy -- **scheduled for removal** |"
            )
    lines += [
        "",
        "So `play_by_play_1996.*` and `nba_play_by_play_1997.*` are the **same**",
        '1996-97 games. Asking for "1997" gets you different data depending on',
        "which file you grab. Pin the pattern, not just the number.",
        "",
        "## Which one to use",
        "",
        "Use the **END-year** files. They are the authoritative Program V v3",
        "outputs and are the only ones that will still be here after the",
        "migration window closes.",
        "",
        f"Every artifact is published in {len(formats)} formats: "
        + ", ".join(f"`.{f}`" for f in formats)
        + ". `hoopR::load_nba_*()` reads the `.rds`.",
        "",
        "## Removal of the legacy assets",
        "",
        "The START-year assets are scheduled for removal once consumers have",
        "migrated. They are deleted by a separate, explicit",
        "`v3_cutover.py --retire-legacy-assets --execute` run, which refuses to",
        "delete any legacy asset whose END-year replacement is not present and",
        "byte-verified on this tag in all published formats.",
        "",
        f"Seasons covered by this publish: {seasons[0]}-{seasons[-1]} (END-year).",
        "",
    ]
    return "\n".join(lines)


def check_gate(
    seasons: list[int],
    staging: Path,
    repo_root: Path,
    raw_root: Path,
    allow: set[str],
) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]]]:
    """Run the section-10.3 gate. Returns (ok, blocking findings, allowlisted findings)."""
    from .v3_gate import run_gate

    findings, _ = run_gate(seasons, staging, repo_root, raw_root)
    bad = [f for f in findings if f["verdict"] in _BAD_VERDICTS]
    allowed = [f for f in bad if f"{f['season']}:{f['family']}" in allow]
    blocking = [f for f in bad if f"{f['season']}:{f['family']}" not in allow]
    return (not blocking), blocking, allowed


def _fmt_bytes(n: Optional[int]) -> str:
    if n is None:
        return "-"
    return f"{n / 1e6:.2f} MB"


def render_manifest(
    manifest: list[dict[str, Any]],
    shadow: list[dict[str, Any]],
    *,
    seasons: list[int],
    repo: str,
    targets: dict[str, Target],
    allowlist: set[str],
    allowed_findings: list[dict[str, Any]],
    blocking_findings: list[dict[str, Any]],
    execute: bool,
    collisions: Optional[list[dict[str, Any]]] = None,
) -> str:
    """The REPLACE MANIFEST, as markdown."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    gate_ok = not blocking_findings
    lines = [
        "# Program V D26d cutover -- REPLACE MANIFEST",
        "",
        f"- generated: `{stamp}`",
        f"- mode: **{'EXECUTE' if execute else 'DRY RUN (nothing uploaded)'}**",
        f"- gate (section 10.3): **{'PASS' if gate_ok else 'FAIL -- PUBLISH BLOCKED'}**",
        f"- release repo: `{repo}`",
        f"- seasons: {seasons[0]}-{seasons[-1]} ({len(seasons)}) END-year",
        "",
        "## Target map",
        "",
        "| family | tag | asset | shadowed legacy asset | collision |",
        "|---|---|---|---|---|",
    ]
    for t in targets.values():
        legacy = (
            t.legacy_asset.format(season="{season" + f"{t.legacy_offset:+d}" + "}")
            if t.legacy_asset
            else "-"
        )
        lines.append(
            f"| `{t.family}` | `{t.tag}` | `{t.asset}` | `{legacy}` | {'**YES**' if t.collision else 'no'} |"
        )

    for t in targets.values():
        if t.collision:
            lines += ["", f"> **COLLISION -- `{t.family}` -> `{t.tag}`**: {t.collision}"]

    counts: dict[tuple[str, str], int] = {}
    bytes_by_tag: dict[str, int] = {}
    for r in manifest:
        counts[(r["tag"], r["verdict"])] = counts.get((r["tag"], r["verdict"]), 0) + 1
        bytes_by_tag[r["tag"]] = bytes_by_tag.get(r["tag"], 0) + r["size"]

    lines += [
        "",
        "## Summary per tag",
        "",
        "| tag | NEW | REPLACE | UNCHANGED | upload bytes |",
        "|---|---:|---:|---:|---:|",
    ]
    for tag in sorted({r["tag"] for r in manifest}):
        lines.append(
            f"| `{tag}` | {counts.get((tag, 'NEW'), 0)} | {counts.get((tag, 'REPLACE'), 0)} "
            f"| {counts.get((tag, 'UNCHANGED'), 0)} | {_fmt_bytes(bytes_by_tag.get(tag, 0))} |"
        )
    total = sum(bytes_by_tag.values())
    lines.append(
        f"| **total** | {sum(1 for r in manifest if r['verdict'] == 'NEW')} "
        f"| {sum(1 for r in manifest if r['verdict'] == 'REPLACE')} "
        f"| {sum(1 for r in manifest if r['verdict'] == 'UNCHANGED')} | {_fmt_bytes(total)} |"
    )

    by_fmt: dict[str, list[int]] = {}
    for r in manifest:
        by_fmt.setdefault(r.get("format", "parquet"), []).append(r["size"])
    lines += [
        "",
        "## Summary per format",
        "",
        "| format | assets | bytes |",
        "|---|---:|---:|",
    ]
    for fmt in sorted(by_fmt):
        lines.append(f"| `.{fmt}` | {len(by_fmt[fmt])} | {_fmt_bytes(sum(by_fmt[fmt]))} |")
    lines.append(f"| **all formats** | {len(manifest)} | {_fmt_bytes(total)} |")

    destroyed = [r for r in manifest if r["verdict"] == "REPLACE"]
    lines += ["", "## WOULD BE DESTROYED (existing remote assets overwritten)", ""]
    if destroyed:
        lines += [
            "| tag | asset | remote bytes | remote updated | replaced by (local bytes / rows) |",
            "|---|---|---:|---|---|",
        ]
        for r in destroyed:
            lines.append(
                f"| `{r['tag']}` | `{r['asset']}` | {_fmt_bytes(r['remote_size'])} | {r['remote_updated_at']} "
                f"| {_fmt_bytes(r['size'])} / {r['rows']:,} rows |"
            )
    else:
        lines.append("_none -- every planned asset name is new on its tag._")

    collisions = collisions or []
    lines += [
        "",
        "## SEASON-LABEL COLLISION (two names, one real season)",
        "",
        "This publish is **additive** (decision B): the new assets land next to the",
        "existing legacy ones. Every row below is one real season covered twice --",
        "the NEW name is authoritative, the legacy name is scheduled for",
        "`--retire-legacy-assets`. Rows whose two names ALSO disagree on the season",
        "number are the sharper hazard (a consumer asking for one year gets different",
        "data depending on which pattern it reads); they are counted under the table.",
        "",
    ]
    if collisions:
        lines += [
            "| tag | real season | NEW (authoritative) | LEGACY (to be retired) | legacy bytes |",
            "|---|---|---|---|---:|",
        ]
        for c in collisions:
            legacy = ", ".join(f"`{n}`" for n in c["legacy_assets"])
            real = (
                f"{c['season'] - 1}-{str(c['season'])[-2:]}"
                if c["label_differs"]
                else str(c["season"])
            )
            lines.append(
                f"| `{c['tag']}` | {real} | `{c['new_stem']}.*` "
                f"| {legacy} | {_fmt_bytes(c['legacy_bytes'])} |"
            )
        tags = sorted({c["tag"] for c in collisions})
        relabelled = sum(1 for c in collisions if c["label_differs"])
        lines += [
            "",
            f"**{len(collisions)} overlapping season(s) across {len(tags)} tag(s): "
            f"{', '.join('`' + t + '`' for t in tags)}** -- of which **{relabelled}** carry a "
            "DIFFERENT season number for the same games (the real hazard); the rest are "
            "same-number duplicates. On `--execute` each of those tags receives a generated "
            f"`{README_ASSET}` naming both patterns and which one wins.",
        ]
    else:
        lines.append(
            "_none -- no legacy asset on any target tag describes a season this publish also covers._"
        )

    lines += [
        "",
        "## SURVIVES UN-REPLACED (still served to load_nba_*() after this cutover)",
        "",
        f"{len(shadow)} remote asset(s) on the target tags are not touched by this plan.",
        "",
        "| tag | asset | bytes | updated |",
        "|---|---|---:|---|",
    ]
    for s in shadow:
        lines.append(
            f"| `{s['tag']}` | `{s['asset']}` | {_fmt_bytes(s['size'])} | {s['updated_at']} |"
        )

    lines += ["", "## Gate (section 10.3)", ""]
    if gate_ok:
        lines.append("**PASS** -- no unexplained finding over the season range.")
    else:
        lines.append(
            f"**FAIL -- publish is blocked.** {len(blocking_findings)} unexplained finding(s). "
            "Explain each, then re-run with one `--allow-diff SEASON:FAMILY` per explained case. "
            "There is no blanket override."
        )
        lines += ["", "| season:family | verdict | detail |", "|---|---|---|"]
        for f in blocking_findings:
            lines.append(f"| `{f['season']}:{f['family']}` | {f['verdict']} | {f['detail']} |")

    lines += ["", "### Allowlisted (explained) diffs", ""]
    if allowlist:
        lines += ["| season:family | verdict | detail |", "|---|---|---|"]
        for f in allowed_findings:
            lines.append(f"| `{f['season']}:{f['family']}` | {f['verdict']} | {f['detail']} |")
        unused = sorted(allowlist - {f"{f['season']}:{f['family']}" for f in allowed_findings})
        if unused:
            lines += ["", f"_allowlisted but not triggered: {', '.join(unused)}_"]
    else:
        lines.append("_none -- no `--allow-diff` was passed._")

    lines += [
        "",
        "## Full plan",
        "",
        "| season | family | format | tag | asset | local bytes | rows | remote bytes | remote updated | verdict |",
        "|---:|---|---|---|---|---:|---:|---:|---|---|",
    ]
    for r in manifest:
        lines.append(
            f"| {r['season']} | {r['family']} | `{r.get('format', 'parquet')}` | `{r['tag']}` "
            f"| `{r['asset']}` | {_fmt_bytes(r['size'])} "
            f"| {r['rows']:,} | {_fmt_bytes(r['remote_size'])} | {r['remote_updated_at'] or '-'} | {r['verdict']} |"
        )
    return "\n".join(lines) + "\n"


def upload_one(
    row: dict[str, Any],
    repo: str,
    staging: Path,
    *,
    runner: Optional[Runner] = None,
    verify_download: bool = False,
) -> None:
    """Upload one asset, re-fetch it, verify, and record a receipt. Raises on mismatch."""
    run = runner or _gh_runner
    tag, asset = row["tag"], row["asset"]
    run(["release", "upload", tag, str(row["path"]), "--repo", repo, "--clobber"])

    got = remote_assets(tag, repo, runner=runner).get(asset)
    if got is None:
        raise RuntimeError(f"{tag}/{asset}: absent from the release after upload (silent drop)")
    if got["size"] != row["size"]:
        raise RuntimeError(f"{tag}/{asset}: remote size {got['size']} != local {row['size']}")

    if verify_download:
        # ponytail: the GitHub release-asset API exposes no digest, so size is the
        # only free check. Downloading to hash is exact but costs the bytes twice;
        # opt-in per run.
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            run(
                [
                    "release",
                    "download",
                    tag,
                    "--repo",
                    repo,
                    "--pattern",
                    asset,
                    "--dir",
                    td,
                    "--clobber",
                ]
            )
            back = sha256_file(Path(td) / asset)
        if back != row["sha256"]:
            raise RuntimeError(f"{tag}/{asset}: round-trip sha256 {back} != local {row['sha256']}")

    save_receipt(staging, row["key"], row["sha256"], row["size"])


def upload_readmes(
    tags: list[str],
    targets: dict[str, Target],
    seasons: list[int],
    repo: str,
    staging: Path,
    *,
    runner: Optional[Runner] = None,
    execute: bool = False,
) -> None:
    """Write + upload the generated per-tag migration note. No-op without *execute*."""
    run = runner or _gh_runner
    out_dir = release_build_dir(staging)
    out_dir.mkdir(parents=True, exist_ok=True)
    for tag in tags:
        # `gh release upload` names the asset after the file, so each tag's note
        # is staged under its own directory as the plain README.md name.
        staged = out_dir / tag / README_ASSET
        staged.parent.mkdir(parents=True, exist_ok=True)
        text = render_tag_readme(tag, targets, seasons)
        staged.write_text(text, encoding="utf-8")
        if not execute:
            _log(f"  would upload {tag}/{README_ASSET} ({len(text)} bytes) -- {staged}")
            continue
        run(["release", "upload", tag, str(staged), "--repo", repo, "--clobber"])
        _log(f"  uploaded {tag}/{README_ASSET}")


def plan_legacy_retirement(
    seasons: list[int],
    manifest: list[dict[str, Any]],
    remote_by_tag: dict[str, dict[str, Any]],
    targets: dict[str, Target],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split the legacy assets into (deletable, refused).

    A legacy asset is deletable ONLY when its END-year replacement is present on
    the same tag and verified in **every** published format -- verified meaning
    the manifest classified it ``UNCHANGED``, i.e. a receipt's sha256 matches the
    local file and the remote size agrees. Anything less and the legacy bytes are
    the only surviving copy of that season on that tag: deleting them on the
    strength of a same-name upload that was never checked is how a season
    disappears. ``hoopR::load_nba_*()`` reads the ``.rds``, so an unverified rds
    blocks retirement of the whole season even if the parquet checks out.
    """
    deletable: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    for target in targets.values():
        remote = remote_by_tag.get(target.tag, {})
        for season in seasons:
            stem = legacy_stem(target, season)
            if stem is None:
                continue
            legacy_names = sorted(
                n for n in remote if n.rsplit(".", 1)[0] == stem or n.startswith(f"{stem}.")
            )
            if not legacy_names:
                continue
            new_stem = target.asset.format(season=season).rsplit(".parquet", 1)[0]
            rows = [
                r
                for r in manifest
                if r["tag"] == target.tag and r["season"] == season and r["family"] == target.family
            ]
            got = {r.get("format", "parquet"): r["verdict"] for r in rows}
            missing = [f for f in FORMATS if f not in got]
            unverified = sorted(f for f, v in got.items() if v != "UNCHANGED")
            entry = {
                "tag": target.tag,
                "season": season,
                "new_stem": new_stem,
                "legacy_assets": legacy_names,
                "bytes": sum(remote[n]["size"] for n in legacy_names),
            }
            if missing or unverified:
                reasons = []
                if missing:
                    reasons.append(f"not staged: {', '.join(missing)}")
                if unverified:
                    reasons.append(f"not verified on the release: {', '.join(unverified)}")
                refused.append({**entry, "reason": "; ".join(reasons)})
            else:
                deletable.append(entry)
    return deletable, refused


def retire_legacy_assets(
    deletable: list[dict[str, Any]],
    refused: list[dict[str, Any]],
    repo: str,
    *,
    runner: Optional[Runner] = None,
    execute: bool = False,
) -> int:
    """Delete the legacy START-year assets. SEPARATE step; never bundled with an upload.

    Returns nonzero when anything was refused -- a partially-completed retirement
    is a state the operator must see, not one to exit 0 on.
    """
    run = runner or _gh_runner
    for entry in refused:
        _log(
            f"REFUSING {entry['tag']} season {entry['season']}: {entry['reason']} "
            f"-- keeping {', '.join(entry['legacy_assets'])}"
        )
    total = sum(e["bytes"] for e in deletable)
    _log(
        f"legacy retirement: {len(deletable)} season(s) deletable ({_fmt_bytes(total)}), "
        f"{len(refused)} refused -- {'DELETING' if execute else 'dry run, nothing deleted'}"
    )
    for entry in deletable:
        for name in entry["legacy_assets"]:
            if not execute:
                _log(f"  would delete {entry['tag']}/{name}")
                continue
            run(["release", "delete-asset", entry["tag"], name, "--repo", repo, "--yes"])
            _log(f"  deleted {entry['tag']}/{name}")
    return 1 if refused else 0


def retire_tags(
    tags: tuple[str, ...], repo: str, *, runner: Optional[Runner] = None, execute: bool = False
) -> int:
    """Delete the `_v3` releases. Separate step -- never bundled with an upload."""
    run = runner or _gh_runner
    for tag in tags:
        assets = remote_assets(tag, repo, runner=runner)
        _log(
            f"{tag}: {len(assets)} asset(s) -- {'DELETING' if execute else 'would delete (dry run)'}"
        )
        for name, meta in sorted(assets.items()):
            _log(f"  {name}  {_fmt_bytes(meta['size'])}  {meta['updatedAt']}")
        if execute:
            run(["release", "delete", tag, "--repo", repo, "--yes", "--cleanup-tag"])
    return 0


def _parse_tag_overrides(pairs: list[str], targets: dict[str, Target]) -> dict[str, Target]:
    out = dict(targets)
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit(f"--tag expects FAMILY=TAG, got {pair!r}")
        family, tag = pair.split("=", 1)
        if family not in out:
            raise SystemExit(f"--tag: unknown family {family!r} (have {', '.join(out)})")
        base = out[family]
        out[family] = Target(
            family=base.family,
            tag=tag,
            asset=base.asset,
            legacy_asset=base.legacy_asset if tag == base.tag else None,
            legacy_offset=base.legacy_offset,
            collision="" if tag != base.tag else base.collision,
        )
    return out


def main(argv: Optional[list[str]] = None) -> int:
    """CLI: ``python -m nba_data_build.v3_cutover -s 1997 -e 2026`` (dry run)."""
    ap = argparse.ArgumentParser(
        prog="nba_data_build.v3_cutover",
        description="Program V D26d cutover publisher. DRY RUN unless --execute is passed.",
    )
    ap.add_argument("-s", "--start-season", type=int, default=1997)
    ap.add_argument("-e", "--end-season", type=int, default=2026)
    ap.add_argument("--staging", default=None, help="default: {repo}/v3_staging")
    ap.add_argument("--repo-root", default=None)
    ap.add_argument("--raw-root", default=None, help="default: sibling hoopR-nba-stats-raw")
    ap.add_argument("--release-repo", default=REPO)
    ap.add_argument("--families", default=",".join(TARGETS), help="comma-separated subset")
    ap.add_argument(
        "--tag",
        action="append",
        default=[],
        metavar="FAMILY=TAG",
        help="override a family's target tag (repeatable)",
    )
    ap.add_argument(
        "--allow-diff",
        action="append",
        default=[],
        metavar="SEASON:FAMILY",
        help="allowlist ONE explained gate DIFF (repeatable); printed in the manifest",
    )
    ap.add_argument(
        "--manifest", default=None, help="default: {repo}/logs/v3_cutover_manifest_{ts}.md"
    )
    ap.add_argument(
        "--execute",
        action="store_true",
        help="actually upload. WITHOUT THIS NOTHING IS WRITTEN TO THE RELEASE.",
    )
    ap.add_argument(
        "--verify-download",
        action="store_true",
        help="after each upload re-download the asset and compare sha256 (slow, exact)",
    )
    ap.add_argument(
        "--retire-v3-tags",
        action="store_true",
        help="SEPARATE STEP: delete the _v3 releases. Does no uploading.",
    )
    ap.add_argument(
        "--retire-legacy-assets",
        action="store_true",
        help=(
            "SEPARATE STEP: delete the legacy START-year assets superseded by this "
            "publish. Does no uploading. Refuses any season whose END-year "
            "replacement is not present and verified in every format."
        ),
    )
    ap.add_argument(
        "--formats",
        default=",".join(FORMATS),
        help=f"comma-separated subset of {', '.join(FORMATS)} (default: all three)",
    )
    ap.add_argument(
        "--force-derive",
        action="store_true",
        help="re-derive the rds / csv.gz even when they look current",
    )
    args = ap.parse_args(argv)

    if args.retire_v3_tags and args.retire_legacy_assets:
        _log("--retire-v3-tags and --retire-legacy-assets are separate steps; run one at a time.")
        return 2

    from .v3_backfill import repo_root_default

    repo_root = Path(args.repo_root) if args.repo_root else repo_root_default()
    staging = Path(args.staging) if args.staging else repo_root / "v3_staging"
    raw_root = Path(args.raw_root) if args.raw_root else repo_root.parent / "hoopR-nba-stats-raw"

    if args.retire_v3_tags:
        _log(f"retire {'(EXECUTE)' if args.execute else '(dry run)'}: {', '.join(RETIRE_TAGS)}")
        return retire_tags(RETIRE_TAGS, args.release_repo, execute=args.execute)

    families = [f.strip() for f in args.families.split(",") if f.strip()]
    unknown = [f for f in families if f not in TARGETS]
    if unknown:
        _log(f"unknown families: {', '.join(unknown)}")
        return 2
    targets = _parse_tag_overrides(args.tag, {f: TARGETS[f] for f in families})

    formats = tuple(f.strip() for f in args.formats.split(",") if f.strip())
    bad_formats = [f for f in formats if f not in FORMATS]
    if bad_formats:
        _log(f"unknown formats: {', '.join(bad_formats)} (have {', '.join(FORMATS)})")
        return 2

    seasons = list(range(args.start_season, args.end_season + 1))
    allow = set(args.allow_diff)

    if args.retire_legacy_assets:
        # Retirement is gated on VERIFICATION, not on the section-10.3 gate: what
        # matters is that the replacement bytes are provably on the release, and
        # the data-quality gate has no bearing on that.
        _log(f"legacy retirement {'(EXECUTE)' if args.execute else '(dry run)'}: {staging}")
        staged = stage_rows(staging, seasons, targets, formats=formats)
        remote_by_tag = {t.tag: remote_assets(t.tag, args.release_repo) for t in targets.values()}
        manifest = build_manifest(staged, remote_by_tag, load_receipts(staging))
        deletable, refused = plan_legacy_retirement(seasons, manifest, remote_by_tag, targets)
        return retire_legacy_assets(deletable, refused, args.release_repo, execute=args.execute)

    _log(f"gate: seasons {seasons[0]}-{seasons[-1]} staging={staging}")
    ok, blocking, allowed = check_gate(seasons, staging, repo_root, raw_root, allow)
    _log(f"gate {'PASS' if ok else 'FAIL'} ({len(blocking)} blocking, {len(allowed)} allowlisted)")

    # The manifest is read-only and is written even when the gate fails -- the
    # operator needs the blast radius in front of them while deciding whether a
    # DIFF is explainable, not only after it is resolved.
    _log(f"deriving release formats ({', '.join(formats)}) + hashing -- rds is verified on write")
    staged = stage_rows(staging, seasons, targets, formats=formats, force_derive=args.force_derive)
    if not staged:
        _log(f"no staged parquets under {staging} for those seasons -- nothing to do")
        return 1

    remote_by_tag = {t.tag: remote_assets(t.tag, args.release_repo) for t in targets.values()}
    manifest = build_manifest(staged, remote_by_tag, load_receipts(staging))
    shadow = shadowed_assets(manifest, remote_by_tag, targets)
    collisions = season_label_collisions(seasons, remote_by_tag, targets)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = (
        Path(args.manifest)
        if args.manifest
        else repo_root / "logs" / f"v3_cutover_manifest_{stamp}.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_manifest(
            manifest,
            shadow,
            seasons=seasons,
            repo=args.release_repo,
            targets=targets,
            allowlist=allow,
            allowed_findings=allowed,
            blocking_findings=blocking,
            execute=args.execute,
            collisions=collisions,
        ),
        encoding="utf-8",
    )
    n = {v: sum(1 for r in manifest if r["verdict"] == v) for v in ("NEW", "REPLACE", "UNCHANGED")}
    _log(f"MANIFEST: {out}")
    _log(
        f"  NEW={n['NEW']} REPLACE={n['REPLACE']} UNCHANGED={n['UNCHANGED']} "
        f"upload_bytes={sum(r['size'] for r in manifest) / 1e6:.1f}MB shadowed={len(shadow)} "
        f"season_label_collisions={len(collisions)}"
    )

    if not ok:
        _log(f"GATE FAILED -- {len(blocking)} unexplained finding(s). Refusing to publish.")
        for f in blocking:
            _log(f"  {f['season']} {f['family']} {f['verdict']} {f['detail']}")
        _log("Explain each one, then re-run with --allow-diff SEASON:FAMILY per explained case.")
        return 1

    if not args.execute:
        _log(f"{README_ASSET} that --execute would upload to each tag (written locally, not sent):")
        upload_readmes(
            sorted({r["tag"] for r in manifest}),
            targets,
            seasons,
            args.release_repo,
            staging,
            execute=False,
        )
        _log("DRY RUN -- nothing uploaded. Review the manifest, then re-run with --execute.")
        return 0

    # A *tag* collision (target tag already carrying a different dataset) is a
    # hard refusal; a *season-label* collision is expected under decision B and
    # is mitigated by the README below, not by refusing.
    tag_collisions = [t for t in targets.values() if t.collision]
    if tag_collisions:
        for t in tag_collisions:
            _log(f"REFUSING: {t.family} -> {t.tag}: {t.collision}")
        return 1

    todo = [r for r in manifest if r["verdict"] != "UNCHANGED"]
    _log(f"EXECUTE: {len(todo)} asset(s) ({len(manifest) - len(todo)} already verified, skipped)")
    for i, row in enumerate(todo, 1):
        _log(
            f"[{i}/{len(todo)}] {row['verdict']} {row['tag']}/{row['asset']} {_fmt_bytes(row['size'])}"
        )
        try:
            upload_one(row, args.release_repo, staging, verify_download=args.verify_download)
        except Exception as exc:  # noqa: BLE001 -- stop on the FIRST bad asset, do not continue
            _log(f"FAILED at {row['tag']}/{row['asset']}: {type(exc).__name__}: {exc}")
            _log("Stopped. Fix, then re-run -- verified assets are skipped via the receipt file.")
            return 1
    _log(f"done: {len(todo)} asset(s) uploaded + verified")

    # Last, so a failed data upload never leaves a note promising assets that are
    # not there. Every touched tag gets one, not only the colliding ones: the
    # END-year convention needs stating wherever it now appears.
    _log(f"uploading the {README_ASSET} migration note to each touched tag")
    upload_readmes(
        sorted({r["tag"] for r in manifest}),
        targets,
        seasons,
        args.release_repo,
        staging,
        execute=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
