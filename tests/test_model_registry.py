"""models/REGISTRY.md carries the nba_player_impact row (Track C guard)."""

from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / "models" / "REGISTRY.md"


def _rows() -> list[str]:
    text = REGISTRY.read_text(encoding="utf-8")
    return [ln for ln in text.splitlines() if ln.startswith("|") and "---" not in ln]


def test_registry_exists():
    assert REGISTRY.is_file(), "models/REGISTRY.md is missing"


def test_impact_row_present_with_card_and_tag():
    row = next((r for r in _rows() if "`nba_player_impact`" in r), None)
    assert row, "no registry row for nba_player_impact"
    assert "nba_player_impact_card.json" in row, "row must name the card sidecar"


def test_deliberate_no_cron_is_stated_honestly():
    text = REGISTRY.read_text(encoding="utf-8")
    assert "dispatch-only BY DESIGN" in text, "the deliberate no-cron decision must stay stated (rate-budgeted build)"
