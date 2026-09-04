"""Binary sensors OptiFamily (attention famille)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CRECHE_ID, CONF_CRECHE_NAME, CONF_ENABLED_ENFANTS, CONF_ENFANTS, DOMAIN
from .coordinator import OptieFamilyCoordinator
from .day_context import compute_family_day
from .models import iter_enfants_enabled


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configure les binary sensors."""
    coordinator: OptieFamilyCoordinator = entry.runtime_data
    async_add_entities([OptieFamilyAttentionBinarySensor(coordinator, entry)])


class OptieFamilyAttentionBinarySensor(
    CoordinatorEntity[OptieFamilyCoordinator], BinarySensorEntity
):
    """True si action à prévoir (déposer / récupérer / messages non lus)."""

    _attr_has_entity_name = True
    _attr_name = "Attention"
    _attr_icon = "mdi:alert-circle-outline"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: OptieFamilyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_attention"

    @property
    def device_info(self) -> DeviceInfo:
        creche_name = self._entry.data.get(CONF_CRECHE_NAME)
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=creche_name or "OptiFamily",
            manufacturer="OptiCrèche",
            model="OptiFamily",
        )

    def _family_ctx(self):
        data = self.coordinator.data
        live = data.enfants if data else []
        enfants = iter_enfants_enabled(
            live,
            self._entry.data.get(CONF_ENFANTS, []),
            enabled_ids=self._entry.options.get(CONF_ENABLED_ENFANTS),
        )
        unread = 0
        if data:
            unread = sum(
                1
                for m in data.messages
                if not m.get("vu", True) and not bool(m.get("sender", False))
            )
        return compute_family_day(
            enfants,
            data.plannings if data else {},
            now=datetime.now(),
            unread_creche=unread,
        )

    @property
    def is_on(self) -> bool:
        return self._family_ctx().attention

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ctx = self._family_ctx()
        return {
            "optifamily_kind": "attention",
            "config_entry_id": self._entry.entry_id,
            "creche_id": self._entry.data.get(CONF_CRECHE_ID),
            "creche_name": self._entry.data.get(CONF_CRECHE_NAME),
            "raison": ctx.attention_raison,
            "phase": ctx.phase,
            "message": ctx.message,
        }
