"""Les copies repo root et composant HACS restent alignées (packages)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "optifamily"


def test_helpers_package_mirrors_root() -> None:
    root = (ROOT / "packages" / "optifamily_helpers.yaml").read_text()
    bundled = (COMPONENT / "packages" / "optifamily_helpers.yaml").read_text()
    assert root == bundled


def test_dashboard_lives_in_component_only() -> None:
    """Source unique : custom_components/optifamily/dashboards/ (plus de copie racine)."""
    bundled = COMPONENT / "dashboards" / "optifamily.yaml"
    assert bundled.is_file()
    assert not (ROOT / "dashboards").exists()


def test_dashboard_transmissions_recap_uses_enriched_chips() -> None:
    """Récap journal : chips enrichis, pas de resume texte en secondary."""
    text = (COMPONENT / "dashboards" / "optifamily.yaml").read_text()
    journal = text.split("  - title: Transmissions\n", 1)[1].split("  - title: Messages\n", 1)[0]
    assert "has_recap" in journal
    assert "changes_pipi" in journal
    assert "changes_caca" in journal
    assert "solides" in journal
    assert "food-apple-outline" in journal
    assert "stats.resume" not in journal
    assert "resume if resume" not in journal
    assert "Aucune transmission pour cette date." in journal
