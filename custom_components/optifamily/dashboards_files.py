"""Copie le YAML dashboard OptiFamily hors GitHub (import Lovelace local)."""

from __future__ import annotations

import logging
from pathlib import Path
import shutil

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_SOURCE = Path(__file__).parent / "dashboards"
_DASHBOARD_NAME = "optifamily.yaml"


def install_dashboard_sync(hass: HomeAssistant) -> bool:
    """Copie le dashboard vers config/optifamily/dashboards/optifamily.yaml."""
    src = _SOURCE / _DASHBOARD_NAME
    if not src.is_file():
        _LOGGER.debug("Dashboard OptiFamily introuvable dans le composant")
        return False
    dest_dir = Path(hass.config.path("optifamily", "dashboards"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / _DASHBOARD_NAME)
    _LOGGER.debug("Dashboard OptiFamily copié vers %s", dest_dir / _DASHBOARD_NAME)
    return True


def uninstall_dashboard_sync(hass: HomeAssistant) -> bool:
    """Retire le dashboard copié (et le dossier s'il est vide)."""
    dest_dir = Path(hass.config.path("optifamily", "dashboards"))
    target = dest_dir / _DASHBOARD_NAME
    removed = False
    if target.is_file():
        target.unlink()
        removed = True
    if dest_dir.is_dir() and not any(dest_dir.iterdir()):
        dest_dir.rmdir()
    parent = dest_dir.parent
    if parent.is_dir() and parent.name == "optifamily" and not any(parent.iterdir()):
        parent.rmdir()
    return removed


async def async_install_dashboard(hass: HomeAssistant) -> None:
    """Copie le dashboard sans bloquer le loop HA."""
    try:
        if await hass.async_add_executor_job(install_dashboard_sync, hass):
            _LOGGER.info(
                "Dashboard OptiFamily (exemple facultatif) copié dans /optifamily/dashboards "
                "— à importer seulement si vous le souhaitez"
            )
    except Exception:
        _LOGGER.exception("Impossible d'installer le dashboard OptiFamily")


async def async_uninstall_dashboard(hass: HomeAssistant) -> None:
    """Supprime le dashboard copié."""
    try:
        if await hass.async_add_executor_job(uninstall_dashboard_sync, hass):
            _LOGGER.info("Dashboard OptiFamily retiré de /optifamily/dashboards")
    except Exception:
        _LOGGER.exception("Impossible de retirer le dashboard OptiFamily")
