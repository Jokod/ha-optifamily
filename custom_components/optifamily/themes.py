"""Installe le thème Lovelace OptiFamily (largeur des sections)."""

from __future__ import annotations

import logging
from pathlib import Path
import shutil

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_SOURCE = Path(__file__).parent / "themes"
_THEME_NAME = "optifamily.yaml"


def install_theme_sync(hass: HomeAssistant) -> bool:
    """Copie le thème vers config/themes/optifamily.yaml."""
    src = _SOURCE / _THEME_NAME
    if not src.is_file():
        _LOGGER.debug("Thème OptiFamily introuvable dans le composant")
        return False
    dest_dir = Path(hass.config.path("themes"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / _THEME_NAME)
    _LOGGER.debug("Thème OptiFamily copié vers %s", dest_dir / _THEME_NAME)
    return True


def uninstall_theme_sync(hass: HomeAssistant) -> bool:
    """Retire le thème OptiFamily de config/themes/."""
    target = Path(hass.config.path("themes", _THEME_NAME))
    if not target.is_file():
        return False
    target.unlink()
    return True


async def async_install_theme(hass: HomeAssistant) -> None:
    """Copie le thème sans bloquer le loop HA."""
    try:
        if await hass.async_add_executor_job(install_theme_sync, hass):
            _LOGGER.info("Thème OptiFamily installé dans /themes (recharger les thèmes)")
    except Exception:
        _LOGGER.exception("Impossible d'installer le thème OptiFamily")


async def async_uninstall_theme(hass: HomeAssistant) -> None:
    """Supprime le thème copié."""
    try:
        if await hass.async_add_executor_job(uninstall_theme_sync, hass):
            _LOGGER.info("Thème OptiFamily retiré de /themes")
    except Exception:
        _LOGGER.exception("Impossible de retirer le thème OptiFamily")
