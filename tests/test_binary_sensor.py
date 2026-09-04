"""Tests unitaires — binary_sensor Attention."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from custom_components.optifamily import binary_sensor as binary_sensor_mod
from custom_components.optifamily.const import CONF_CRECHE_ID, CONF_CRECHE_NAME, CONF_ENFANTS
from custom_components.optifamily.coordinator import OptieFamilyData


@pytest.mark.asyncio
async def test_binary_sensor_attention(hass: MagicMock) -> None:
    data = OptieFamilyData()
    data.enfants = [{"id": 1, "libelle": "Alice"}]
    day = date.today()
    data.plannings = {
        1: {
            "semaines": [
                {
                    "journees": [
                        {
                            "date": day.isoformat(),
                            "creneaux": [
                                {
                                    "type": "regulier",
                                    "label": (
                                        f"{(datetime.now().hour + 1) % 24:02d}:00 - "
                                        f"{(datetime.now().hour + 8) % 24:02d}:00"
                                    ),
                                }
                            ],
                        }
                    ]
                }
            ]
        }
    }
    data.messages = [
        {"vu": False, "sender": False},
        {"vu": True, "sender": False},
        {"vu": False, "sender": True},
    ]

    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {
        CONF_CRECHE_ID: 1001,
        CONF_CRECHE_NAME: "Crèche",
        CONF_ENFANTS: [{"id": 1, "libelle": "Alice"}],
    }
    entry.options = {}
    coordinator = MagicMock()
    coordinator.data = data
    entry.runtime_data = coordinator

    added: list[object] = []
    await binary_sensor_mod.async_setup_entry(hass, entry, added.extend)
    assert len(added) == 1
    sensor = added[0]
    assert sensor.device_info["name"] == "Crèche"
    _ = sensor.is_on
    attrs = sensor.extra_state_attributes
    assert attrs["optifamily_kind"] == "attention"
    assert attrs["creche_id"] == 1001

    coordinator.data = None
    entry2 = MagicMock()
    entry2.entry_id = "e2"
    entry2.data = {}
    entry2.options = {}
    empty = binary_sensor_mod.OptieFamilyAttentionBinarySensor(coordinator, entry2)
    assert empty.device_info["name"] == "OptiFamily"
    assert empty.is_on is False
    assert empty.extra_state_attributes["raison"] == "RAS"
