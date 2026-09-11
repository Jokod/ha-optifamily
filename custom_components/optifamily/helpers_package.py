"""Installe le package helpers OptiFamily (silencieux / scripts)."""

from __future__ import annotations

import logging
from pathlib import Path
import shutil

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_SOURCE = Path(__file__).parent / "packages"
_PACKAGE_NAME = "optifamily_helpers.yaml"


def install_package_sync(hass: HomeAssistant) -> bool:
    """Copie (écrase) le package vers config/packages/optifamily_helpers.yaml."""
    src = _SOURCE / _PACKAGE_NAME
    if not src.is_file():
        _LOGGER.debug("Package helpers OptiFamily introuvable dans le composant")
        return False
    dest_dir = Path(hass.config.path("packages"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / _PACKAGE_NAME)
    _LOGGER.debug("Package helpers OptiFamily copié vers %s", dest_dir / _PACKAGE_NAME)
    return True


def uninstall_package_sync(hass: HomeAssistant) -> bool:
    """Retire le package helpers de config/packages/."""
    target = Path(hass.config.path("packages", _PACKAGE_NAME))
    if not target.is_file():
        return False
    target.unlink()
    return True


async def async_install_package(hass: HomeAssistant) -> None:
    """Copie le package sans bloquer le loop HA."""
    try:
        if await hass.async_add_executor_job(install_package_sync, hass):
            _LOGGER.info(
                "Package helpers OptiFamily installé dans /packages "
                "(nécessite packages: !include_dir_named packages + redémarrage)"
            )
    except Exception:
        _LOGGER.exception("Impossible d'installer le package helpers OptiFamily")


async def async_uninstall_package(hass: HomeAssistant) -> None:
    """Supprime le package helpers copié."""
    try:
        if await hass.async_add_executor_job(uninstall_package_sync, hass):
            _LOGGER.info("Package helpers OptiFamily retiré de /packages")
    except Exception:
        _LOGGER.exception("Impossible de retirer le package helpers OptiFamily")
