"""Installation automatique du thème Lovelace."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.optifamily import themes as th


def test_install_theme_sync_copies_yaml(hass: MagicMock, tmp_path: Path) -> None:
    assert th.install_theme_sync(hass) is True
    dest = tmp_path / "themes" / "optifamily.yaml"
    assert dest.is_file()
    text = dest.read_text()
    assert "ha-view-sections-column-max-width" in text
    assert "optifamily-accent" in text
    assert "optifamily-radius" in text


def test_install_theme_missing_source(hass: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(th, "_SOURCE", Path("/tmp/optifamily-no-themes"))
    assert th.install_theme_sync(hass) is False


def test_uninstall_theme_sync(hass: MagicMock, tmp_path: Path) -> None:
    th.install_theme_sync(hass)
    assert th.uninstall_theme_sync(hass) is True
    assert not (tmp_path / "themes" / "optifamily.yaml").exists()
    assert th.uninstall_theme_sync(hass) is False


@pytest.mark.asyncio
async def test_async_theme_swallows_errors(
    hass: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(th, "install_theme_sync", MagicMock(side_effect=RuntimeError("boom")))
    await th.async_install_theme(hass)
    monkeypatch.setattr(th, "uninstall_theme_sync", MagicMock(side_effect=RuntimeError("boom")))
    await th.async_uninstall_theme(hass)


@pytest.mark.asyncio
async def test_async_install_and_uninstall_log_success(
    hass: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    await th.async_install_theme(hass)
    assert "installé" in caplog.text
    await th.async_uninstall_theme(hass)
    assert "retiré" in caplog.text
