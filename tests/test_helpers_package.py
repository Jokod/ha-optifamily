"""Installation automatique du package helpers OptiFamily."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.optifamily import helpers_package as pkg


def test_install_package_sync_copies_yaml(hass: MagicMock, tmp_path: Path) -> None:
    assert pkg.install_package_sync(hass) is True
    dest = tmp_path / "packages" / "optifamily_helpers.yaml"
    assert dest.is_file()
    text = dest.read_text()
    assert "optifamily_quiet_hours" in text
    assert "optifamily_notify_resume" in text


def test_install_package_missing_source(hass: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pkg, "_SOURCE", Path("/tmp/optifamily-no-packages"))
    assert pkg.install_package_sync(hass) is False


def test_uninstall_package_sync(hass: MagicMock, tmp_path: Path) -> None:
    pkg.install_package_sync(hass)
    assert pkg.uninstall_package_sync(hass) is True
    assert not (tmp_path / "packages" / "optifamily_helpers.yaml").exists()
    assert pkg.uninstall_package_sync(hass) is False


def test_install_overwrites_on_update(hass: MagicMock, tmp_path: Path) -> None:
    dest = tmp_path / "packages" / "optifamily_helpers.yaml"
    dest.parent.mkdir(parents=True)
    dest.write_text("# old custom\n")
    assert pkg.install_package_sync(hass) is True
    assert "optifamily_quiet_hours" in dest.read_text()
    assert "# old custom" not in dest.read_text()


@pytest.mark.asyncio
async def test_async_package_swallows_errors(
    hass: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pkg, "install_package_sync", MagicMock(side_effect=RuntimeError("boom")))
    await pkg.async_install_package(hass)
    monkeypatch.setattr(pkg, "uninstall_package_sync", MagicMock(side_effect=RuntimeError("boom")))
    await pkg.async_uninstall_package(hass)


@pytest.mark.asyncio
async def test_async_install_and_uninstall_log_success(
    hass: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    await pkg.async_install_package(hass)
    assert "Package helpers" in caplog.text
    await pkg.async_uninstall_package(hass)
    assert "retiré" in caplog.text
