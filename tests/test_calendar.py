"""Tests du calendrier OptiFamily."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.optifamily import calendar as calendar_mod
from custom_components.optifamily.coordinator import OptieFamilyData
from custom_components.optifamily.models import Enfant


@pytest.mark.asyncio
async def test_calendar_setup_and_events(
    planning_present: dict, today: date, hass: MagicMock
) -> None:
    data = OptieFamilyData()
    data.enfants = [{"id": 1, "libelle": "Alice"}]
    data.plannings = {1: planning_present}

    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {"creche_name": "Crèche", "enfants": [{"id": 1, "libelle": "Alice"}]}
    entry.options = {}

    coordinator = MagicMock()
    coordinator.data = data
    coordinator.known_calendar_enfant_ids = set()
    coordinator.async_get_planning_month = AsyncMock(return_value=planning_present)
    listeners: list[Any] = []

    def add_listener(cb: Any) -> Any:
        listeners.append(cb)
        return lambda: None

    coordinator.async_add_listener = add_listener
    entry.runtime_data = coordinator
    entry.async_on_unload = MagicMock()

    added: list[Any] = []

    def async_add_entities(entities: list[Any]) -> None:
        added.extend(entities)

    await calendar_mod.async_setup_entry(hass, entry, async_add_entities)
    assert any(isinstance(e, calendar_mod.OptieFamilyFamilyCalendar) for e in added)
    assert any(isinstance(e, calendar_mod.OptieFamilyChildCalendar) for e in added)

    family = next(e for e in added if isinstance(e, calendar_mod.OptieFamilyFamilyCalendar))
    child = next(e for e in added if isinstance(e, calendar_mod.OptieFamilyChildCalendar))
    assert family.device_info["name"] == "Crèche"
    assert child.extra_state_attributes["enfant_libelle"] == "Alice"
    assert family.extra_state_attributes["optifamily_kind"] == "planning_family"
    assert family.entity_id.startswith("calendar.optifamily_planning_")

    start = datetime.combine(today - timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(today + timedelta(days=2), datetime.min.time(), tzinfo=UTC)
    family_events = await family.async_get_events(hass, start, end)
    child_events = await child.async_get_events(hass, start, end)
    naive_start = datetime.combine(today - timedelta(days=1), datetime.min.time())
    naive_end = datetime.combine(today + timedelta(days=2), datetime.min.time())
    naive_events = await family.async_get_events(hass, naive_start, naive_end)
    assert naive_events
    mixed = calendar_mod._aware(datetime(2026, 1, 1, 8, 0))
    assert mixed.tzinfo is not None
    already = calendar_mod._aware(datetime(2026, 1, 1, 8, 0, tzinfo=UTC))
    assert already.tzinfo is UTC
    assert family_events
    assert child_events
    assert family_events[0].summary.startswith("Alice")

    _ = family.event
    _ = child.event

    coordinator.data = None
    listeners[0]()
    coordinator.data = data
    before = len(added)
    listeners[0]()
    assert len(added) == before
    data.enfants = [{"id": 1, "libelle": "Alice"}, {"id": 2, "libelle": "Bob"}]
    listeners[0]()
    assert any(getattr(e, "_enfant", None) and e._enfant.id == 2 for e in added)

    entry2 = MagicMock()
    entry2.entry_id = "e2"
    entry2.data = {}
    family2 = calendar_mod.OptieFamilyFamilyCalendar(coordinator, entry2)
    coordinator.data = None
    assert family2.event is None
    assert family2.device_info["name"] == "OptiFamily"

    empty_child = calendar_mod.OptieFamilyChildCalendar(
        coordinator, entry2, Enfant(id=9, libelle="Z"), "hub-device-id"
    )
    assert empty_child.event is None
    assert empty_child.device_info["name"] == "Z"
    assert empty_child.device_info["via_device_id"] == "hub-device-id"
    assert calendar_mod._event_end(type("E", (), {"end": date(2026, 1, 2)})()).day == 2
    assert (
        calendar_mod._event_start(
            type("E", (), {"start": datetime(2026, 1, 1, 8, 0, tzinfo=UTC)})()
        ).hour
        == 8
    )
    assert calendar_mod._event_start(type("E", (), {"start": date(2026, 1, 1)})()).day == 1
    assert (
        calendar_mod._event_end(
            type("E", (), {"end": datetime(2026, 1, 1, 9, 0, tzinfo=UTC)})()
        ).hour
        == 9
    )
    assert (
        calendar_mod._event_start(type("E", (), {"start": datetime(2026, 1, 1, 8, 0)})()).year
        == 2026
    )
    assert calendar_mod._event_end(type("E", (), {"end": datetime(2026, 1, 1, 9, 0)})()).hour >= 0
    first = type("E", (), {"uid": "a", "start": 1, "end": 2, "summary": "x"})()
    dup = type("E", (), {"uid": "a", "start": 1, "end": 2, "summary": "x"})()
    other = type("E", (), {"uid": "b", "start": 1, "end": 2, "summary": "y"})()
    assert len(calendar_mod._dedupe_calendar_events([first, dup, other])) == 2
