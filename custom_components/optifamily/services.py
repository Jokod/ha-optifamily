"""Services OptiFamily (journal des transmissions)."""

from __future__ import annotations

from datetime import date, datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DOMAIN
from .coordinator import OptieFamilyCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_TRANSMISSIONS_DATE = "set_transmissions_date"
SERVICE_SHIFT_TRANSMISSIONS_DATE = "shift_transmissions_date"

_SET_SCHEMA = vol.Schema(
    {
        vol.Required("date"): cv.date,
        vol.Optional("config_entry_id"): cv.string,
    }
)
_SHIFT_SCHEMA = vol.Schema(
    {
        vol.Required("days", default=-1): vol.All(vol.Coerce(int), vol.Range(min=-30, max=30)),
        vol.Optional("config_entry_id"): cv.string,
    }
)


def _parse_day(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _coordinators(
    hass: HomeAssistant, entry_id: str | None = None
) -> list[tuple[ConfigEntry, OptieFamilyCoordinator]]:
    out: list[tuple[ConfigEntry, OptieFamilyCoordinator]] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry_id and entry.entry_id != entry_id:
            continue
        coordinator = getattr(entry, "runtime_data", None)
        if isinstance(coordinator, OptieFamilyCoordinator):
            out.append((entry, coordinator))
    return out


async def _async_set_date(call: ServiceCall) -> None:
    day = _parse_day(call.data["date"])
    entry_id = call.data.get("config_entry_id")
    targets = _coordinators(call.hass, entry_id)
    if not targets:
        _LOGGER.warning("Aucun coordinator OptiFamily pour set_transmissions_date")
        return
    for _entry, coordinator in targets:
        await coordinator.async_set_transmissions_view_date(day)


async def _async_shift_date(call: ServiceCall) -> None:
    days = int(call.data["days"])
    entry_id = call.data.get("config_entry_id")
    targets = _coordinators(call.hass, entry_id)
    if not targets:
        _LOGGER.warning("Aucun coordinator OptiFamily pour shift_transmissions_date")
        return
    for _entry, coordinator in targets:
        await coordinator.async_shift_transmissions_view_date(days)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Enregistre les services une seule fois."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_TRANSMISSIONS_DATE):
        return
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TRANSMISSIONS_DATE,
        _async_set_date,
        schema=_SET_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SHIFT_TRANSMISSIONS_DATE,
        _async_shift_date,
        schema=_SHIFT_SCHEMA,
    )


@callback
def async_unload_services(hass: HomeAssistant) -> None:
    """Retire les services s'il ne reste aucune entrée."""
    if hass.config_entries.async_entries(DOMAIN):
        return
    if hass.services.has_service(DOMAIN, SERVICE_SET_TRANSMISSIONS_DATE):
        hass.services.async_remove(DOMAIN, SERVICE_SET_TRANSMISSIONS_DATE)
    if hass.services.has_service(DOMAIN, SERVICE_SHIFT_TRANSMISSIONS_DATE):
        hass.services.async_remove(DOMAIN, SERVICE_SHIFT_TRANSMISSIONS_DATE)
