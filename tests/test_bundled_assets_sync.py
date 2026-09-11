"""Les copies repo root et composant HACS restent alignées."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "optifamily"


def test_helpers_package_mirrors_root() -> None:
    root = (ROOT / "packages" / "optifamily_helpers.yaml").read_text()
    bundled = (COMPONENT / "packages" / "optifamily_helpers.yaml").read_text()
    assert root == bundled


def test_dashboard_mirrors_root() -> None:
    root = (ROOT / "dashboards" / "optifamily.yaml").read_text()
    bundled = (COMPONENT / "dashboards" / "optifamily.yaml").read_text()
    assert root == bundled
