"""Appareils Home Assistant pour OptiFamily (crèche / hub)."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import CONF_CRECHE_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


@callback
def async_get_or_create_hub_device_id(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """Crée (ou récupère) l'appareil crèche et retourne son `device_id`.

    Les appareils enfants doivent référencer ce hub via `via_device_id`
    (le paramètre `via_device` est déprécié depuis HA 2026.8, retiré en 2027.8).
    """
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_CRECHE_NAME) or "OptiFamily",
        manufacturer="OptiCrèche",
        model="OptiFamily",
    )
    return device.id


@callback
def async_purge_enfant_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    enfant_ids: set[int] | list[int],
) -> int:
    """Supprime devices + entités des enfants exclus du suivi."""
    if not enfant_ids:
        return 0
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)
    removed = 0
    for enfant_id in enfant_ids:
        identifier = (DOMAIN, f"{entry.entry_id}_{enfant_id}")
        device = device_reg.async_get_device(identifiers={identifier})
        if device is not None:
            _LOGGER.info(
                "Suppression du device OptiFamily enfant %s (entry %s)",
                enfant_id,
                entry.entry_id,
            )
            device_reg.async_remove_device(device.id)
            removed += 1
            continue
        # Entités orphelines (unique_id préfixé) si le device a déjà disparu
        prefix = f"{entry.entry_id}_{enfant_id}_"
        for entity in list(entity_reg.entities.values()):
            if entity.config_entry_id != entry.entry_id:
                continue
            if (entity.unique_id or "").startswith(prefix):
                entity_reg.async_remove(entity.entity_id)
                removed += 1
    return removed
