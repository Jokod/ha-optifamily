"""Tests unitaires — registry devices / purge enfants exclus."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.optifamily import devices as devices_mod


def test_purge_enfant_devices(hass: MagicMock) -> None:
    entry = MagicMock()
    entry.entry_id = "e1"
    assert devices_mod.async_purge_enfant_devices(hass, entry, []) == 0

    device = SimpleNamespace(id="dev-1")
    device_reg = MagicMock()
    device_reg.async_get_device = MagicMock(return_value=device)
    device_reg.async_remove_device = MagicMock()

    orphan = SimpleNamespace(
        entity_id="sensor.optifamily_e1_2_present",
        unique_id="e1_2_present",
        config_entry_id="e1",
    )
    other = SimpleNamespace(
        entity_id="sensor.other",
        unique_id="other",
        config_entry_id="other",
    )
    entity_reg = MagicMock()
    entity_reg.entities = {"a": orphan, "b": other}
    entity_reg.async_remove = MagicMock()

    with (
        patch(
            "custom_components.optifamily.devices.dr.async_get",
            return_value=device_reg,
        ),
        patch(
            "custom_components.optifamily.devices.er.async_get",
            return_value=entity_reg,
        ),
    ):
        # device found for id 1
        assert devices_mod.async_purge_enfant_devices(hass, entry, [1]) == 1
        device_reg.async_remove_device.assert_called_with("dev-1")

        # no device → orphan entities for id 2
        device_reg.async_get_device = MagicMock(return_value=None)
        assert devices_mod.async_purge_enfant_devices(hass, entry, {2}) == 1
        entity_reg.async_remove.assert_called_with("sensor.optifamily_e1_2_present")
