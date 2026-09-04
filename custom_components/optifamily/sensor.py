"""Capteurs Home Assistant pour OptiFamily."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
import logging
from typing import Any, ClassVar

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CRECHE_NAME, CONF_ENFANTS, DOMAIN
from .coordinator import OptieFamilyCoordinator, OptieFamilyData
from .devices import async_get_or_create_hub_device_id
from .models import (
    Enfant,
    build_enfants_summary,
    flatten_planning_jours,
    format_creneau_labels,
    get_presence,
    get_today_creneaux,
    iter_enfants,
    normalize_transmissions,
    transmissions_markdown,
)

_LOGGER = logging.getLogger(__name__)


def _messages_from_sender(messages: list[dict[str, Any]], *, from_me: bool) -> list[dict[str, Any]]:
    """Filtre les messages selon l'expéditeur (`sender=true` = parent connecté)."""
    return [m for m in messages if bool(m.get("sender", False)) is from_me]


def _unread_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Messages non lus (`vu=false`)."""
    return [m for m in messages if not m.get("vu", True)]


def _message_sensor_attrs(data: OptieFamilyData, *, from_me: bool) -> dict[str, Any]:
    """Attributs pour un capteur messages (parent ou crèche)."""
    subset = _messages_from_sender(data.messages, from_me=from_me)
    unread = _unread_messages(subset)
    return {
        "origine": "moi" if from_me else "creche",
        "total": len(subset),
        "non_lus": len(unread),
        "last_message_date": subset[0].get("date") if subset else None,
        "last_unread_date": unread[0].get("date") if unread else None,
    }


@dataclass(frozen=True, kw_only=True)
class OptieFamilySensorDescription(SensorEntityDescription):
    """Description enrichie avec un extracteur de valeur."""

    value_fn: Callable[[OptieFamilyData], Any] = lambda d: None
    attributes_fn: Callable[[OptieFamilyData], dict[str, Any]] | None = None


GLOBAL_SENSORS: tuple[OptieFamilySensorDescription, ...] = (
    OptieFamilySensorDescription(
        key="enfants",
        name="Enfants",
        icon="mdi:human-male-female-child",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: build_enfants_summary(d)["count"],
        attributes_fn=lambda d: build_enfants_summary(d),
    ),
    OptieFamilySensorDescription(
        key="enfants_presents",
        name="Enfants en crèche aujourd'hui",
        icon="mdi:baby-carriage",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: build_enfants_summary(d)["presents_aujourdhui"],
        attributes_fn=lambda d: {
            "noms": build_enfants_summary(d)["noms_presents"],
            "liste": build_enfants_summary(d)["liste"],
        },
    ),
    OptieFamilySensorDescription(
        key="messages_unread_creche",
        name="Messages non lus (crèche)",
        icon="mdi:message-badge",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(_unread_messages(_messages_from_sender(d.messages, from_me=False))),
        attributes_fn=lambda d: _message_sensor_attrs(d, from_me=False),
    ),
    OptieFamilySensorDescription(
        key="messages_unread_me",
        name="Messages non lus (moi)",
        icon="mdi:message-reply-text",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(_unread_messages(_messages_from_sender(d.messages, from_me=True))),
        attributes_fn=lambda d: _message_sensor_attrs(d, from_me=True),
    ),
    OptieFamilySensorDescription(
        key="actualites_total",
        name="Actualités",
        icon="mdi:newspaper-variant-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.actualites.get("total", 0),
    ),
    OptieFamilySensorDescription(
        key="documents_total",
        name="Documents",
        icon="mdi:file-document-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (
            len(d.documents)
            + len(getattr(d, "documents_famille", None) or [])
            + sum(len(v) for v in (getattr(d, "documents_enfant", None) or {}).values())
        ),
        attributes_fn=lambda d: {
            "creche": len(d.documents),
            "famille": len(getattr(d, "documents_famille", None) or []),
            "enfants": {
                str(eid): len(items)
                for eid, items in (getattr(d, "documents_enfant", None) or {}).items()
            },
        },
    ),
    OptieFamilySensorDescription(
        key="facturation_total",
        name="Factures",
        icon="mdi:receipt",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.facturation),
    ),
)


def _get_enfants(coordinator: OptieFamilyCoordinator, entry: ConfigEntry) -> list[Enfant]:
    """Liste fusionnée des enfants (API + config entry persistée)."""
    live = coordinator.data.enfants if coordinator.data else []
    persisted = entry.data.get(CONF_ENFANTS, [])
    return iter_enfants(live, persisted)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configure tous les capteurs au démarrage."""
    coordinator: OptieFamilyCoordinator = entry.runtime_data
    via_device_id = async_get_or_create_hub_device_id(hass, entry)

    entities: list[SensorEntity] = []

    for description in GLOBAL_SENSORS:
        entities.append(OptieFamilyGlobalSensor(coordinator, description, entry))

    entities.append(OptieFamilyLastRefreshSensor(coordinator, entry))

    for enfant in _get_enfants(coordinator, entry):
        coordinator.known_enfant_ids.add(enfant.id)
        entities.extend(_build_child_sensors(coordinator, entry, enfant, via_device_id))

    async_add_entities(entities)

    @callback
    def _handle_coordinator_update() -> None:
        """Ajoute dynamiquement les capteurs des nouveaux enfants."""
        if not coordinator.data:
            return
        hub_id = async_get_or_create_hub_device_id(hass, entry)
        new_entities: list[SensorEntity] = []
        for enfant in _get_enfants(coordinator, entry):
            if enfant.id in coordinator.known_enfant_ids:
                continue
            coordinator.known_enfant_ids.add(enfant.id)
            _LOGGER.info("Ajout des capteurs pour l'enfant %s (%s)", enfant.libelle, enfant.id)
            new_entities.extend(_build_child_sensors(coordinator, entry, enfant, hub_id))
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_handle_coordinator_update))


def _build_child_sensors(
    coordinator: OptieFamilyCoordinator,
    entry: ConfigEntry,
    enfant: Enfant,
    via_device_id: str,
) -> list[SensorEntity]:
    """Crée les capteurs pour un enfant donné."""
    return [
        OptieFamilyChildPresentSensor(coordinator, entry, enfant, via_device_id),
        OptieFamilyChildPlanningSlotsSensor(coordinator, entry, enfant, via_device_id),
        OptieFamilyChildTransmissionsSensor(coordinator, entry, enfant, via_device_id),
        OptieFamilyChildTransmissionsJournalSensor(coordinator, entry, enfant, via_device_id),
        OptieFamilyChildAlbumsSensor(coordinator, entry, enfant, via_device_id),
    ]


class _OptieFamilyBaseSensor(CoordinatorEntity[OptieFamilyCoordinator], SensorEntity):
    """Base commune à tous les capteurs OptiFamily."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OptieFamilyCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        creche_name = self._entry.data.get(CONF_CRECHE_NAME)
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=creche_name or "OptiFamily",
            manufacturer="OptiCrèche",
            model="OptiFamily",
            entry_type=None,
        )


class OptieFamilyGlobalSensor(_OptieFamilyBaseSensor):
    """Capteur basé sur une OptieFamilySensorDescription."""

    def __init__(
        self,
        coordinator: OptieFamilyCoordinator,
        description: OptieFamilySensorDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attrs: dict[str, Any] = {
            "optifamily_kind": self.entity_description.key,
        }
        if self.entity_description.attributes_fn:
            attrs.update(self.entity_description.attributes_fn(self.coordinator.data))
        return attrs


class OptieFamilyLastRefreshSensor(_OptieFamilyBaseSensor):
    """Horodatage du dernier rafraîchissement API réussi."""

    _attr_name = "Dernier rafraîchissement"
    _attr_icon = "mdi:clock-check-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: OptieFamilyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_dernier_rafraichissement"

    @property
    def native_value(self) -> Any:
        return getattr(self.coordinator, "last_sync_at", None)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        interval = getattr(self.coordinator, "scan_interval", None)
        return {
            "optifamily_kind": "dernier_rafraichissement",
            "intervalle_secondes": interval,
            "intervalle_minutes": (interval // 60) if interval else None,
        }


class _ChildSensor(_OptieFamilyBaseSensor):
    """Base pour les capteurs liés à un enfant."""

    def __init__(
        self,
        coordinator: OptieFamilyCoordinator,
        entry: ConfigEntry,
        enfant: Enfant,
        sensor_key: str,
        via_device_id: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._enfant = enfant
        self._via_device_id = via_device_id
        self._attr_unique_id = f"{entry.entry_id}_{enfant.id}_{sensor_key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{self._enfant.id}")},
            name=self._enfant.libelle,
            manufacturer="OptiCrèche",
            model="OptiFamily - Enfant",
            via_device_id=self._via_device_id,
        )


class OptieFamilyChildPresentSensor(_ChildSensor):
    """Indique si l'enfant est présent aujourd'hui (créneau régulier)."""

    _attr_name = "Présent aujourd'hui"
    _attr_icon = "mdi:baby-face-outline"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = ["présent", "absent", "inconnu"]

    def __init__(
        self,
        coordinator: OptieFamilyCoordinator,
        entry: ConfigEntry,
        enfant: Enfant,
        via_device_id: str,
    ) -> None:
        super().__init__(coordinator, entry, enfant, "present", via_device_id)

    @property
    def native_value(self) -> str:
        planning = self.coordinator.data.plannings.get(self._enfant.id)
        return get_presence(planning)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        planning = self.coordinator.data.plannings.get(self._enfant.id)
        creneaux = get_today_creneaux(planning)
        return {
            "enfant_id": self._enfant.id,
            "enfant_libelle": self._enfant.libelle,
            "optifamily_kind": "present",
            "creneaux": format_creneau_labels(creneaux),
            "creneaux_libelle": " · ".join(format_creneau_labels(creneaux)),
            "creneaux_detail": [
                {
                    "type": c.get("type"),
                    "label": c.get("label"),
                    "details": c.get("details"),
                }
                for c in creneaux
            ],
        }


class OptieFamilyChildPlanningSlotsSensor(_ChildSensor):
    """Nombre de créneaux ce mois-ci."""

    _attr_name = "Créneaux ce mois"
    _attr_icon = "mdi:calendar-month"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: OptieFamilyCoordinator,
        entry: ConfigEntry,
        enfant: Enfant,
        via_device_id: str,
    ) -> None:
        super().__init__(coordinator, entry, enfant, "planning_slots", via_device_id)

    @property
    def native_value(self) -> int:
        planning = self.coordinator.data.plannings.get(self._enfant.id)
        if not planning:
            return 0
        count = 0
        for semaine in planning.get("semaines", []):
            for journee in semaine.get("journees", []):
                count += len(
                    [c for c in journee.get("creneaux", []) if c.get("type") == "regulier"]
                )
        return count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        planning = self.coordinator.data.plannings.get(self._enfant.id)
        if not planning:
            return {
                "enfant_id": self._enfant.id,
                "enfant_libelle": self._enfant.libelle,
                "optifamily_kind": "planning_slots",
            }
        return {
            "enfant_id": self._enfant.id,
            "enfant_libelle": self._enfant.libelle,
            "optifamily_kind": "planning_slots",
            "label": planning.get("label"),
            "previous": planning.get("previous"),
            "next": planning.get("next"),
            "jours": flatten_planning_jours(planning),
        }


class OptieFamilyChildTransmissionsSensor(_ChildSensor):
    """Nombre de transmissions du jour (+ détail)."""

    _attr_name = "Transmissions du jour"
    _attr_icon = "mdi:clipboard-text-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: OptieFamilyCoordinator,
        entry: ConfigEntry,
        enfant: Enfant,
        via_device_id: str,
    ) -> None:
        super().__init__(coordinator, entry, enfant, "transmissions", via_device_id)

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.transmissions.get(self._enfant.id, []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        raw = self.coordinator.data.transmissions.get(self._enfant.id, [])
        items = normalize_transmissions(raw)
        return {
            "enfant_id": self._enfant.id,
            "enfant_libelle": self._enfant.libelle,
            "optifamily_kind": "transmissions",
            "count": len(items),
            "date": date.today().isoformat(),
            "items": items,
            "lignes": [i["ligne"] for i in items],
            "markdown": transmissions_markdown(
                raw, enfant_libelle=self._enfant.libelle, jour=date.today().isoformat()
            ),
        }


class OptieFamilyChildTransmissionsJournalSensor(_ChildSensor):
    """Journal des transmissions pour la date naviguée (services set/shift)."""

    _attr_name = "Journal transmissions"
    _attr_icon = "mdi:book-open-page-variant-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: OptieFamilyCoordinator,
        entry: ConfigEntry,
        enfant: Enfant,
        via_device_id: str,
    ) -> None:
        super().__init__(coordinator, entry, enfant, "transmissions_journal", via_device_id)

    @property
    def native_value(self) -> int:
        raw = self.coordinator.transmissions_journal.get(self._enfant.id)
        if raw is None:
            raw = self.coordinator.data.transmissions.get(self._enfant.id, [])
        return len(raw or [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        day = self.coordinator.transmissions_view_date
        raw = self.coordinator.transmissions_journal.get(self._enfant.id)
        if raw is None and day == date.today():
            raw = self.coordinator.data.transmissions.get(self._enfant.id, [])
        raw = raw or []
        items = normalize_transmissions(raw)
        return {
            "enfant_id": self._enfant.id,
            "enfant_libelle": self._enfant.libelle,
            "optifamily_kind": "transmissions_journal",
            "date": day.isoformat(),
            "count": len(items),
            "items": items,
            "lignes": [i["ligne"] for i in items],
            "markdown": transmissions_markdown(
                raw, enfant_libelle=self._enfant.libelle, jour=day.isoformat()
            ),
        }


class OptieFamilyChildAlbumsSensor(_ChildSensor):
    """Nombre d'albums disponibles."""

    _attr_name = "Albums"
    _attr_icon = "mdi:image-multiple-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: OptieFamilyCoordinator,
        entry: ConfigEntry,
        enfant: Enfant,
        via_device_id: str,
    ) -> None:
        super().__init__(coordinator, entry, enfant, "albums", via_device_id)

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.albums.get(self._enfant.id, []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "enfant_id": self._enfant.id,
            "enfant_libelle": self._enfant.libelle,
            "optifamily_kind": "albums",
            "count": self.native_value,
        }
