"""Numbered-stage inventory gate.

This repo has NO R dataset chain — the R/ directory holds scrape stages and
helpers, not dataset builders — so there is nothing to pair across languages.
The contract here is therefore Python-internal: the ``DATASETS`` registry, the
numbered shims beside the package, and the stage numbers must agree.

Why it exists: the registry is the thing the build actually iterates, but the
directory listing is what a human reads. When those two drift, the listing
stops being the pipeline — a dataset gets built with no visible stage, or a
stage file advertises a dataset the package cannot build and fails only when
someone runs it.

Stage numbers follow registry order, which is the intended BUILD order
(``shots`` derives from ``pbp``, so it sorts after it). They are not the
execution schedule: the daily driver builds every dataset in one ``reshape``
invocation and stays the sequence truth. Holes are allowed and never compacted
— a retired dataset leaves its number behind rather than renumbering the rest.

Portability: this engine derives the family prefix and the registry module from
the repo layout, so the file is byte-identical in the WNBA twin. Any diff
between the two copies is drift, not a league difference.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE_SUFFIX = "_data_build"


def _package_dir() -> Path:
    """The single ``python/<league>_data_build/`` package in this repo."""
    hits = sorted(p for p in (REPO / "python").glob(f"*{PACKAGE_SUFFIX}") if p.is_dir())
    assert len(hits) == 1, (
        f"expected exactly one python/*{PACKAGE_SUFFIX}/ under {REPO}, "
        f"found {[h.name for h in hits]}"
    )
    return hits[0]


def _registry_path() -> Path:
    """``datasets.py`` wherever it lives in the package (top level or a subpackage)."""
    hits = sorted(_package_dir().rglob("datasets.py"))
    assert hits, f"no datasets.py under {_package_dir()}"
    # A subpackage copy (reshape/datasets.py) is the build registry; prefer the
    # one that actually declares DATASETS if several exist.
    declaring = [p for p in hits if _try_keys(p) is not None]
    assert len(declaring) == 1, (
        "expected exactly one datasets.py declaring DATASETS, found "
        f"{[str(p.relative_to(REPO)) for p in declaring]}"
    )
    return declaring[0]


def _try_keys(path: Path) -> list[str] | None:
    """Ordered dataset keys from a ``DATASETS`` tuple-of-Dataset literal, or None."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        tgs = [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
        if not any(isinstance(t, ast.Name) and t.id == "DATASETS" for t in tgs):
            continue
        keys = []
        for elt in node.value.elts:
            assert isinstance(elt, ast.Call) and elt.args, (
                "each DATASETS row is a Dataset(...) call"
            )
            keys.append(ast.literal_eval(elt.args[0]))
        return keys
    return None


def _registry_keys() -> list[str]:
    keys = _try_keys(_registry_path())
    assert keys is not None
    return keys


def _family() -> str:
    """Stage-file prefix, e.g. ``nba_stats`` — derived from the release tags."""
    text = _registry_path().read_text(encoding="utf-8")
    tags = re.findall(r'"([a-z]+_stats)_[a-z_0-9]+"', text)
    assert tags, f"no <family>_stats_* release tag found in {_registry_path()}"
    uniq = sorted(set(tags))
    assert len(uniq) == 1, f"registry mixes families {uniq}"
    return uniq[0]


def _shims() -> dict[str, tuple[str, Path]]:
    """key -> (NN, path) for the numbered stage shims."""
    pattern = re.compile(rf"^{re.escape(_family())}_(?P<num>\d{{2}})_(?P<key>.+)_creation$")
    found: dict[str, tuple[str, Path]] = {}
    dupes = []
    for path in sorted((REPO / "python").glob("*.py")):
        m = pattern.match(path.stem)
        if not m:
            continue
        key, num = m.group("key"), m.group("num")
        if num == "99":
            # Stage 99 is reserved for the schedule-master creation script
            # (spec D16/D34): it builds the master + manifest over EVERY
            # dataset, so it is deliberately not a per-dataset shim and has
            # no registry entry.
            continue
        if key in found:
            dupes.append(key)
        found[key] = (num, path)
    assert not dupes, f"duplicate stage keys among the shims: {sorted(set(dupes))}"
    return found


def _declared_dataset(path: Path) -> str:
    """The ``DATASET = "..."`` constant inside a shim."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        tgs = [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
        if any(isinstance(t, ast.Name) and t.id == "DATASET" for t in tgs):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{path.name} has no DATASET constant")


def test_layout_is_discoverable():
    """The engine self-configures; if discovery is wrong every result below is."""
    assert _registry_path().is_file()
    assert _family()
    assert _registry_keys(), "registry parsed empty"
    assert _shims(), "no numbered stage shims found"


def test_every_dataset_has_a_shim():
    missing = sorted(set(_registry_keys()) - set(_shims()))
    assert not missing, (
        f"registry datasets with no numbered shim: {missing}\n"
        "A dataset the package builds but no stage file exposes is invisible in "
        "the directory listing."
    )


def test_no_shim_without_a_dataset():
    extra = sorted(set(_shims()) - set(_registry_keys()))
    assert not extra, (
        f"numbered shims with no registry entry: {extra}\n"
        "This shim would fail only when someone ran it."
    )


def test_shim_constant_matches_its_filename():
    """A copy-pasted shim that kept the wrong DATASET would build the wrong
    dataset under a correct-looking name — the worst kind of silent failure."""
    wrong = [
        (path.name, key, _declared_dataset(path))
        for key, (_num, path) in sorted(_shims().items())
        if _declared_dataset(path) != key
    ]
    assert not wrong, "shim filename and DATASET constant disagree:\n" + "\n".join(
        f"  {name}: filename says {key!r}, DATASET says {declared!r}"
        for name, key, declared in wrong
    )


def test_stage_numbers_follow_registry_order():
    """Numbers encode intended build order, so they must ascend with the registry.

    Holes are fine (a retired dataset keeps its number); what is not fine is two
    stages out of sequence relative to the order the package builds them in.
    """
    order = {key: i for i, key in enumerate(_registry_keys())}
    numbered = sorted(
        ((int(num), key) for key, (num, _p) in _shims().items() if key in order),
    )
    out_of_order = [
        (prev_key, prev_num, key, num)
        for (prev_num, prev_key), (num, key) in zip(numbered, numbered[1:])
        if order[prev_key] > order[key]
    ]
    assert not out_of_order, "stage numbers disagree with registry build order:\n" + "\n".join(
        f"  {a} ({an:02d}) precedes {b} ({bn:02d}), but the registry builds {b} first"
        for a, an, b, bn in out_of_order
    )


def test_stage_numbers_are_unique():
    nums = [num for num, _p in _shims().values()]
    dupes = sorted({n for n in nums if nums.count(n) > 1})
    assert not dupes, f"stage numbers reused: {dupes} — numbers are dataset identities"
