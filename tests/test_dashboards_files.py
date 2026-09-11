"""Installation automatique du YAML dashboard OptiFamily."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.optifamily import dashboards_files as dash


def test_install_dashboard_sync_copies_yaml(hass: MagicMock, tmp_path: Path) -> None:
    assert dash.install_dashboard_sync(hass) is True
    dest = tmp_path / "optifamily" / "dashboards" / "optifamily.yaml"
    assert dest.is_file()
    assert "title: OptiFamily" in dest.read_text()


def test_install_dashboard_missing_source(hass: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dash, "_SOURCE", Path("/tmp/optifamily-no-dashboards"))
    assert dash.install_dashboard_sync(hass) is False


def test_uninstall_dashboard_sync(hass: MagicMock, tmp_path: Path) -> None:
    dash.install_dashboard_sync(hass)
    assert dash.uninstall_dashboard_sync(hass) is True
    assert not (tmp_path / "optifamily" / "dashboards" / "optifamily.yaml").exists()
    assert not (tmp_path / "optifamily").exists()
    assert dash.uninstall_dashboard_sync(hass) is False


def test_uninstall_keeps_sibling_files(hass: MagicMock, tmp_path: Path) -> None:
    dash.install_dashboard_sync(hass)
    sibling = tmp_path / "optifamily" / "dashboards" / "notes.txt"
    sibling.write_text("keep")
    assert dash.uninstall_dashboard_sync(hass) is True
    assert sibling.is_file()
    assert (tmp_path / "optifamily" / "dashboards").is_dir()


@pytest.mark.asyncio
async def test_async_dashboard_swallows_errors(
    hass: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dash, "install_dashboard_sync", MagicMock(side_effect=RuntimeError("boom")))
    await dash.async_install_dashboard(hass)
    monkeypatch.setattr(
        dash, "uninstall_dashboard_sync", MagicMock(side_effect=RuntimeError("boom"))
    )
    await dash.async_uninstall_dashboard(hass)


@pytest.mark.asyncio
async def test_async_install_and_uninstall_log_success(
    hass: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    await dash.async_install_dashboard(hass)
    assert "facultatif" in caplog.text or "Dashboard OptiFamily" in caplog.text
    await dash.async_uninstall_dashboard(hass)
    assert "retiré" in caplog.text
