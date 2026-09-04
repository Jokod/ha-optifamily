"""Installe et retire uniquement les blueprints OptiFamily (liste nominative)."""

from __future__ import annotations

import logging
from pathlib import Path
import shutil

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_SOURCE = Path(__file__).parent / "blueprints"
_KINDS = ("automation", "script")
# Noms exacts expédiés — jamais d'autre fichier, jamais un rmtree du dossier.
_SHIPPED: dict[str, frozenset[str]] = {
    "automation": frozenset(
        {
            "bilan_soir_famille.yaml",
            "changement_presence.yaml",
            "messages_seuil.yaml",
            "nouveau_document.yaml",
            "nouveau_message.yaml",
            "nouvelle_actualite.yaml",
            "nouvelle_facture.yaml",
            "nouvelle_photo.yaml",
            "rappel_creche_famille.yaml",
            "rappel_creche_matin.yaml",
            "rappel_creneau.yaml",
            "transmissions_du_jour.yaml",
        }
    ),
    "script": frozenset({"resume_famille.yaml"}),
}


def install_blueprints_sync(hass: HomeAssistant) -> int:
    """Copie les YAML vers config/blueprints/{automation,script}/optifamily/."""
    copied = 0
    if not _SOURCE.is_dir():
        _LOGGER.debug("Aucun dossier blueprints dans le composant OptiFamily")
        return 0
    for kind in _KINDS:
        src = _SOURCE / kind
        if not src.is_dir():
            continue
        dest = Path(hass.config.path("blueprints", kind, "optifamily"))
        dest.mkdir(parents=True, exist_ok=True)
        allowed = _SHIPPED.get(kind, frozenset())
        for yaml_file in src.glob("*.yaml"):
            if yaml_file.name not in allowed:
                continue
            shutil.copy2(yaml_file, dest / yaml_file.name)
            copied += 1
        _LOGGER.debug("Blueprints OptiFamily (%s) copiés vers %s", kind, dest)
    return copied


def uninstall_blueprints_sync(hass: HomeAssistant) -> int:
    """Supprime seulement les fichiers listés dans `_SHIPPED`, dans optifamily/."""
    removed = 0
    for kind in _KINDS:
        dest = Path(hass.config.path("blueprints", kind, "optifamily"))
        if not dest.is_dir():
            continue
        for name in _SHIPPED.get(kind, ()):
            target = dest / name
            if target.is_file():
                target.unlink()
                removed += 1
        try:
            leftover = next(dest.iterdir(), None)
        except OSError:
            leftover = object()
            _LOGGER.debug("Dossier blueprints %s inaccessible", dest)
        if leftover is None:
            dest.rmdir()
    return removed


async def async_install_blueprints(hass: HomeAssistant) -> None:
    """Copie les blueprints sans bloquer le loop HA."""
    try:
        copied = await hass.async_add_executor_job(install_blueprints_sync, hass)
        if copied:
            _LOGGER.info("%s blueprint(s) OptiFamily installé(s) dans /blueprints", copied)
    except Exception:
        _LOGGER.exception("Impossible d'installer les blueprints OptiFamily automatiquement")


async def async_uninstall_blueprints(hass: HomeAssistant) -> None:
    """Supprime les blueprints copiés (dernière instance de l'intégration)."""
    try:
        removed = await hass.async_add_executor_job(uninstall_blueprints_sync, hass)
        if removed:
            _LOGGER.info("%s blueprint(s) OptiFamily retiré(s) de /blueprints", removed)
    except Exception:
        _LOGGER.exception("Impossible de retirer les blueprints OptiFamily")
