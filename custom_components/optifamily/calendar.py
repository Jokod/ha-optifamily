"""Calendrier Home Assistant des créneaux OptiFamily."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CRECHE_NAME, DOMAIN
from .coordinator import OptieFamilyCoordinator
from .models import Enfant, iter_year_months, planning_to_events
from .sensor import _get_enfants

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configure un calendrier par enfant."""
    coordinator: OptieFamilyCoordinator = entry.runtime_data
    entities: list[CalendarEntity] = [
        OptieFamilyFamilyCalendar(coordinator, entry),
    ]
    for enfant in _get_enfants(coordinator, entry):
        coordinator.known_calendar_enfant_ids.add(enfant.id)
        entities.append(OptieFamilyChildCalendar(coordinator, entry, enfant))
    async_add_entities(entities)

    @callback
    def _handle_coordinator_update() -> None:
        if not coordinator.data:
            return
        new_entities: list[OptieFamilyChildCalendar] = []
        for enfant in _get_enfants(coordinator, entry):
            if enfant.id in coordinator.known_calendar_enfant_ids:
                continue
            coordinator.known_calendar_enfant_ids.add(enfant.id)
            _LOGGER.info("Ajout du calendrier pour l'enfant %s (%s)", enfant.libelle, enfant.id)
            new_entities.append(OptieFamilyChildCalendar(coordinator, entry, enfant))
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_handle_coordinator_update))


class OptieFamilyFamilyCalendar(CoordinatorEntity[OptieFamilyCoordinator], CalendarEntity):
    """Tous les créneaux de la crèche, pour la carte Lovelace mois par mois."""

    _attr_has_entity_name = False
    _attr_name = "OptiFamily Planning"
    _attr_icon = "mdi:calendar-clock"
    _attr_suggested_object_id = "optifamily_planning"

    def __init__(self, coordinator: OptieFamilyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_planning_calendar_family"
        self.entity_id = "calendar.optifamily_planning"

    @property
    def device_info(self) -> DeviceInfo:
        creche_name = self._entry.data.get(CONF_CRECHE_NAME)
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=creche_name or "OptiFamily",
            manufacturer="OptiCrèche",
            model="OptiFamily",
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"optifamily_kind": "planning_family"}

    @property
    def event(self) -> CalendarEvent | None:
        now = datetime.now().astimezone()
        upcoming = [e for e in self._current_month_events() if _event_end(e) > now]
        upcoming.sort(key=_event_start)
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        collected: list[CalendarEvent] = []
        start_date = _aware(start_date)
        end_date = _aware(end_date)
        for enfant in _get_enfants(self.coordinator, self._entry):
            for year, month in iter_year_months(start_date, end_date):
                planning = await self.coordinator.async_get_planning_month(enfant.id, year, month)
                collected.extend(self._events_from_planning(planning, enfant.libelle, year, month))
        return _dedupe_calendar_events(
            [
                event
                for event in collected
                if _event_start(event) < end_date and _event_end(event) > start_date
            ]
        )

    def _current_month_events(self) -> list[CalendarEvent]:
        if not self.coordinator.data:
            return []
        today = datetime.now().date()
        events: list[CalendarEvent] = []
        for enfant in _get_enfants(self.coordinator, self._entry):
            planning = self.coordinator.data.plannings.get(enfant.id)
            events.extend(
                self._events_from_planning(planning, enfant.libelle, today.year, today.month)
            )
        return events

    def _events_from_planning(
        self,
        planning: dict[str, Any] | None,
        libelle: str,
        year: int | None = None,
        month: int | None = None,
    ) -> list[CalendarEvent]:
        return _calendar_events_from_planning(planning, libelle, year=year, month=month)


class OptieFamilyChildCalendar(CoordinatorEntity[OptieFamilyCoordinator], CalendarEntity):
    """Créneaux de présence d'un enfant, navigables mois par mois."""

    _attr_has_entity_name = True
    _attr_name = "Planning"
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: OptieFamilyCoordinator,
        entry: ConfigEntry,
        enfant: Enfant,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._enfant = enfant
        self._attr_unique_id = f"{entry.entry_id}_{enfant.id}_planning_calendar"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{self._enfant.id}")},
            name=self._enfant.libelle,
            manufacturer="OptiCrèche",
            model="OptiFamily - Enfant",
            via_device=(DOMAIN, self._entry.entry_id),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "optifamily_kind": "planning",
            "enfant_id": self._enfant.id,
            "enfant_libelle": self._enfant.libelle,
        }

    @property
    def event(self) -> CalendarEvent | None:
        """Prochain créneau à venir (état de l'entité calendrier)."""
        now = datetime.now().astimezone()
        events = self._events_from_planning(
            (self.coordinator.data.plannings or {}).get(self._enfant.id)
            if self.coordinator.data
            else None,
            now.year,
            now.month,
        )
        upcoming = [e for e in events if _event_end(e) > now]
        upcoming.sort(key=_event_start)
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Événements pour la vue calendrier (charge les mois demandés)."""
        collected: list[CalendarEvent] = []
        start_date = _aware(start_date)
        end_date = _aware(end_date)
        for year, month in iter_year_months(start_date, end_date):
            planning = await self.coordinator.async_get_planning_month(self._enfant.id, year, month)
            collected.extend(self._events_from_planning(planning, year, month))
        return _dedupe_calendar_events(
            [
                event
                for event in collected
                if _event_start(event) < end_date and _event_end(event) > start_date
            ]
        )

    def _events_from_planning(
        self,
        planning: dict[str, Any] | None,
        year: int | None = None,
        month: int | None = None,
    ) -> list[CalendarEvent]:
        return _calendar_events_from_planning(
            planning, self._enfant.libelle, year=year, month=month
        )


def _calendar_events_from_planning(
    planning: dict[str, Any] | None,
    enfant_libelle: str,
    *,
    year: int | None = None,
    month: int | None = None,
) -> list[CalendarEvent]:
    tzinfo = datetime.now().astimezone().tzinfo
    return [
        CalendarEvent(
            start=item.start,
            end=item.end,
            summary=item.summary,
            description=item.description,
            uid=item.uid,
        )
        for item in planning_to_events(planning, enfant_libelle, tzinfo, year=year, month=month)
    ]


def _dedupe_calendar_events(events: list[CalendarEvent]) -> list[CalendarEvent]:
    """Un événement par uid (ou début/fin/titre si uid absent)."""
    unique: list[CalendarEvent] = []
    seen: set[str] = set()
    for event in events:
        key = event.uid or f"{event.start}|{event.end}|{event.summary}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique


def _aware(value: datetime) -> datetime:
    """Datetime comparable (fuseau local si naïf)."""
    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=datetime.now().astimezone().tzinfo)


def _event_start(event: CalendarEvent) -> datetime:
    start = event.start
    if isinstance(start, datetime):
        return _aware(start)
    return _aware(datetime.combine(start, datetime.min.time()))


def _event_end(event: CalendarEvent) -> datetime:
    end = event.end
    if isinstance(end, datetime):
        return _aware(end)
    return _aware(datetime.combine(end, datetime.min.time()))
