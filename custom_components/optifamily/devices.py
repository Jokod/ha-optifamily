"""Appareils Home Assistant pour OptiFamily (crèche / hub)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import CONF_CRECHE_NAME, DOMAIN


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
