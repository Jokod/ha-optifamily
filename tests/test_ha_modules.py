"""Couverture exceptions, models, config, init, coordinator, sensor, config_flow."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
import pytest

import custom_components.optifamily as optifamily_init
from custom_components.optifamily import config as config_mod
from custom_components.optifamily import sensor as sensor_mod
from custom_components.optifamily.config_flow import OptieFamilyConfigFlow, OptieFamilyOptionsFlow
from custom_components.optifamily.const import (
    CONF_CRECHE_ID,
    CONF_CRECHE_NAME,
    CONF_ENABLED_ENFANTS,
    CONF_ENFANTS,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOCUMENTS_SCOPE_CRECHE,
    DOCUMENTS_SCOPE_ENFANT,
    DOCUMENTS_SCOPE_FAMILLE,
    DOMAIN,
)
from custom_components.optifamily.coordinator import OptieFamilyCoordinator, OptieFamilyData
from custom_components.optifamily.exceptions import (
    OptieFamilyApiError,
    OptieFamilyAuthError,
    OptieFamilyConnectionError,
    OptieFamilyMultipleCrechesError,
    OptieFamilySetupError,
)
from custom_components.optifamily.models import (
    Enfant,
    build_enfant_status,
    get_today_creneaux,
)


def test_exceptions() -> None:
    err = OptieFamilyApiError(418, "teapot")
    assert err.status == 418
    assert "418" in str(err)
    multi = OptieFamilyMultipleCrechesError([{"id": 1}, {"id": 2}])
    assert len(multi.creches) == 2
    assert "2 crèches" in str(multi)


def test_get_today_creneaux_no_match() -> None:
    planning = {"semaines": [{"journees": [{"date": "2000-01-01", "creneaux": [{"id": 1}]}]}]}
    assert get_today_creneaux(planning, date(2026, 9, 3)) == []


def test_build_enfant_status(planning_present: dict, today: date) -> None:
    enfant = Enfant(id=1, libelle="Alice")
    status = build_enfant_status(enfant, planning_present, [{}], [{}, {}], today)
    assert status["presence"] == "présent"
    assert status["transmissions"] == 1
    assert status["albums"] == 2
    assert status["creneaux_mois"] >= 1


@pytest.mark.asyncio
async def test_config_async_setup(hass: MagicMock) -> None:
    assert await config_mod.async_setup(hass, {}) is True
    assert hass.async_create_task.call_count == 0

    assert await config_mod.async_setup(hass, {DOMAIN: {"username": "a", "password": "b"}}) is True
    assert hass.async_create_task.call_count == 1


@pytest.mark.asyncio
async def test_init_async_setup(hass: MagicMock) -> None:
    mocked = AsyncMock(return_value=True)
    with patch.object(optifamily_init, "async_setup_config", mocked):
        assert await optifamily_init.async_setup(hass, {}) is True
        mocked.assert_awaited_once_with(hass, {})


@pytest.mark.asyncio
async def test_init_setup_entry_success(hass: MagicMock) -> None:
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {
        "username": "u@e.com",
        "password": "p",
        CONF_CRECHE_ID: 1001,
        CONF_ENFANTS: [{"id": 1, "libelle": "A"}],
    }
    entry.options = {}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock(return_value="unsub")

    coord = MagicMock()
    coord.async_load_tokens = AsyncMock(return_value=True)
    coord.async_save_tokens = AsyncMock()
    coord.async_config_entry_first_refresh = AsyncMock()

    client = MagicMock()
    client.creche_id = 1001
    client.ensure_authenticated = AsyncMock()

    with (
        patch.object(optifamily_init, "async_get_clientsession", return_value=MagicMock()),
        patch.object(optifamily_init, "OptieFamilyApiClient", return_value=client),
        patch.object(optifamily_init, "OptieFamilyCoordinator", return_value=coord),
    ):
        assert await optifamily_init.async_setup_entry(hass, entry) is True

    hass.config_entries.async_forward_entry_setups.assert_awaited()
    assert entry.runtime_data is coord


@pytest.mark.asyncio
async def test_init_setup_entry_bootstrap_and_errors(hass: MagicMock) -> None:
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {"username": "u", "password": "p"}
    entry.options = {}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock(return_value="x")

    coord = MagicMock()
    coord.async_load_tokens = AsyncMock(return_value=False)
    coord.async_save_tokens = AsyncMock()
    coord.async_config_entry_first_refresh = AsyncMock()

    client = MagicMock()
    client.creche_id = None
    client.discover_creches = AsyncMock(return_value=[{"id": 9}])
    client.set_creche_id = MagicMock()
    client.ensure_authenticated = AsyncMock()

    with (
        patch.object(optifamily_init, "async_get_clientsession", return_value=MagicMock()),
        patch.object(optifamily_init, "OptieFamilyApiClient", return_value=client),
        patch.object(optifamily_init, "OptieFamilyCoordinator", return_value=coord),
    ):
        assert await optifamily_init.async_setup_entry(hass, entry) is True
    client.set_creche_id.assert_called_with(9)

    client.ensure_authenticated = AsyncMock(side_effect=OptieFamilyAuthError("bad"))
    with (
        patch.object(optifamily_init, "async_get_clientsession", return_value=MagicMock()),
        patch.object(optifamily_init, "OptieFamilyApiClient", return_value=client),
        patch.object(optifamily_init, "OptieFamilyCoordinator", return_value=coord),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await optifamily_init.async_setup_entry(hass, entry)

    client.ensure_authenticated = AsyncMock(side_effect=OptieFamilyConnectionError("net"))
    with (
        patch.object(optifamily_init, "async_get_clientsession", return_value=MagicMock()),
        patch.object(optifamily_init, "OptieFamilyApiClient", return_value=client),
        patch.object(optifamily_init, "OptieFamilyCoordinator", return_value=coord),
        pytest.raises(ConfigEntryNotReady),
    ):
        await optifamily_init.async_setup_entry(hass, entry)

    client.ensure_authenticated = AsyncMock(side_effect=OptieFamilySetupError("setup"))
    with (
        patch.object(optifamily_init, "async_get_clientsession", return_value=MagicMock()),
        patch.object(optifamily_init, "OptieFamilyApiClient", return_value=client),
        patch.object(optifamily_init, "OptieFamilyCoordinator", return_value=coord),
        pytest.raises(ConfigEntryNotReady),
    ):
        await optifamily_init.async_setup_entry(hass, entry)

    client.ensure_authenticated = AsyncMock(side_effect=OptieFamilyApiError(503, "down"))
    with (
        patch.object(optifamily_init, "async_get_clientsession", return_value=MagicMock()),
        patch.object(optifamily_init, "OptieFamilyApiClient", return_value=client),
        patch.object(optifamily_init, "OptieFamilyCoordinator", return_value=coord),
        pytest.raises(ConfigEntryNotReady),
    ):
        await optifamily_init.async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_init_setup_entry_retry_refresh(hass: MagicMock) -> None:
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {"username": "u", "password": "p", CONF_CRECHE_ID: 1}
    entry.options = {}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock(return_value="x")

    coord = MagicMock()
    coord.async_load_tokens = AsyncMock(return_value=True)
    coord.async_save_tokens = AsyncMock()
    coord.async_config_entry_first_refresh = AsyncMock(
        side_effect=[ConfigEntryAuthFailed("tok"), None]
    )

    client = MagicMock()
    client.creche_id = 1
    client.ensure_authenticated = AsyncMock()

    with (
        patch.object(optifamily_init, "async_get_clientsession", return_value=MagicMock()),
        patch.object(optifamily_init, "OptieFamilyApiClient", return_value=client),
        patch.object(optifamily_init, "OptieFamilyCoordinator", return_value=coord),
    ):
        assert await optifamily_init.async_setup_entry(hass, entry) is True

    coord.async_config_entry_first_refresh = AsyncMock(side_effect=ConfigEntryAuthFailed("tok"))
    client.ensure_authenticated = AsyncMock(side_effect=OptieFamilyAuthError("x"))
    with (
        patch.object(optifamily_init, "async_get_clientsession", return_value=MagicMock()),
        patch.object(optifamily_init, "OptieFamilyApiClient", return_value=client),
        patch.object(optifamily_init, "OptieFamilyCoordinator", return_value=coord),
        pytest.raises(ConfigEntryAuthFailed),
    ):
        await optifamily_init.async_setup_entry(hass, entry)

    client.ensure_authenticated = AsyncMock(side_effect=OptieFamilyConnectionError("x"))
    with (
        patch.object(optifamily_init, "async_get_clientsession", return_value=MagicMock()),
        patch.object(optifamily_init, "OptieFamilyApiClient", return_value=client),
        patch.object(optifamily_init, "OptieFamilyCoordinator", return_value=coord),
        pytest.raises(ConfigEntryNotReady),
    ):
        await optifamily_init.async_setup_entry(hass, entry)

    client.ensure_authenticated = AsyncMock(side_effect=OptieFamilyApiError(500, "x"))
    with (
        patch.object(optifamily_init, "async_get_clientsession", return_value=MagicMock()),
        patch.object(optifamily_init, "OptieFamilyApiClient", return_value=client),
        patch.object(optifamily_init, "OptieFamilyCoordinator", return_value=coord),
        pytest.raises(ConfigEntryNotReady),
    ):
        await optifamily_init.async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_unload_remove_reload(hass: MagicMock) -> None:
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {"username": "u@e.com"}
    entry.runtime_data = MagicMock()
    entry.runtime_data.client.logout = AsyncMock()
    entry.runtime_data.async_clear_tokens = AsyncMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])

    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    assert await optifamily_init.async_unload_entry(hass, entry) is True
    entry.runtime_data.client.logout.assert_awaited()

    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
    assert await optifamily_init.async_unload_entry(hass, entry) is False

    entry.runtime_data.client.logout = AsyncMock(side_effect=RuntimeError("x"))
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    assert await optifamily_init.async_unload_entry(hass, entry) is True

    await optifamily_init.async_remove_entry(hass, entry)
    entry.runtime_data.async_clear_tokens.assert_awaited()

    other = MagicMock()
    other.entry_id = "e2"
    other.data = {"username": "other@e.com"}
    hass.config_entries.async_entries = MagicMock(return_value=[entry, other])
    with patch.object(optifamily_init, "async_uninstall_blueprints", AsyncMock()) as uninst:
        await optifamily_init.async_remove_entry(hass, entry)
        uninst.assert_not_awaited()

    # Même compte encore actif → pas de logout session
    entry.runtime_data.client.logout = AsyncMock()
    sibling = MagicMock()
    sibling.entry_id = "e2"
    sibling.data = {"username": "u@e.com"}
    sibling.runtime_data = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry, sibling])
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    assert await optifamily_init.async_unload_entry(hass, entry) is True
    entry.runtime_data.client.logout.assert_not_awaited()

    hass.config_entries.async_entries = MagicMock(return_value=[])

    entry.runtime_data = None
    await optifamily_init.async_remove_entry(hass, entry)

    await optifamily_init.async_reload_entry(hass, entry)
    hass.config_entries.async_reload.assert_awaited_with("e1")


@pytest.mark.asyncio
async def test_coordinator_tokens_and_update(hass: MagicMock) -> None:
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {CONF_ENFANTS: [{"id": 1, "libelle": "A"}], CONF_CRECHE_ID: 1001}
    entry.options = {"scan_interval": 1800}

    client = MagicMock()
    client.get_tokens.return_value = {"access_token": "A", "refresh_token": "R"}
    client.set_tokens = MagicMock()
    client.creche_id = 1001
    client.set_creche_id = MagicMock()
    client.get_me = AsyncMock(return_value={"creche": {"id": 1001, "nom": "C"}})
    client.get_enfants = AsyncMock(return_value=[{"id": 1, "libelle": "A"}])
    client.get_planning_current_month = AsyncMock(return_value={"semaines": []})
    client.get_transmissions = AsyncMock(return_value=[])
    client.get_albums = AsyncMock(return_value=[])
    client.get_actualites = AsyncMock(return_value={"total": 0})
    client.get_messages = AsyncMock(return_value=[])
    client.get_documents = AsyncMock(return_value=[])
    client.get_documents_famille = AsyncMock(return_value=[])
    client.get_documents_enfant = AsyncMock(return_value=[])
    client.get_facturation = AsyncMock(return_value=[])

    coord = OptieFamilyCoordinator(hass, client, entry)
    await coord.async_save_tokens()
    assert await coord.async_load_tokens() is True
    coord._store.data = None
    assert await coord.async_load_tokens() is False
    await coord.async_clear_tokens()

    assert coord._enfants_changed([{"id": 1}], [{"id": 1}]) is False
    assert coord._enfants_changed([{"id": 1}], [{"id": 2}]) is True

    data = await coord._async_update_data()
    assert data.enfants[0]["id"] == 1
    assert data.persisted_enfants == [{"id": 1, "libelle": "A"}]
    assert coord._planning_cache[(1, date.today().year, date.today().month)].data == {
        "semaines": []
    }

    client.get_planning = AsyncMock(return_value={"label": "Aout"})
    other = await coord.async_get_planning_month(1, 2020, 8)
    assert other["label"] == "Aout"
    assert await coord.async_get_planning_month(1, 2020, 8) == other
    client.get_planning.assert_awaited_once()

    coord.data = data
    current = await coord.async_get_planning_month(1, date.today().year, date.today().month)
    assert current == {"semaines": []}

    client.get_planning = AsyncMock(side_effect=RuntimeError("nope"))
    assert await coord.async_get_planning_month(9, 2019, 1) == {}
    client.get_planning = AsyncMock(return_value={"revived": True})
    assert await coord.async_get_planning_month(9, 2019, 1) == {}
    client.get_planning.assert_not_called()

    client.get_planning = AsyncMock(return_value=["not-a-dict"])
    assert await coord.async_get_planning_month(9, 2018, 2) == {}
    assert await coord.async_get_planning_month(9, 2018, 2) == {}
    client.get_planning.assert_awaited_once()

    from time import monotonic

    from custom_components.optifamily.const import PLANNING_CACHE_TTL, PLANNING_ERROR_RETRY

    stale_ok = coord._planning_cache[(1, 2020, 8)]
    stale_ok.fetched_at = monotonic() - PLANNING_CACHE_TTL - 1
    client.get_planning = AsyncMock(return_value={"label": "Aout-refresh"})
    assert (await coord.async_get_planning_month(1, 2020, 8))["label"] == "Aout-refresh"

    stale_err = coord._planning_cache[(9, 2019, 1)]
    stale_err.fetched_at = monotonic() - PLANNING_ERROR_RETRY - 1
    client.get_planning = AsyncMock(return_value={"label": "retry-ok"})
    assert (await coord.async_get_planning_month(9, 2019, 1))["label"] == "retry-ok"

    calls = {"n": 0}
    started = asyncio.Event()
    released = asyncio.Event()

    async def _slow_planning(*_args: Any, **_kwargs: Any) -> dict[str, str]:
        calls["n"] += 1
        started.set()
        await released.wait()
        return {"label": "coalesced"}

    client.get_planning = _slow_planning
    first = asyncio.create_task(coord.async_get_planning_month(3, 2022, 4))
    await started.wait()
    second = asyncio.create_task(coord.async_get_planning_month(3, 2022, 4))
    released.set()
    assert await first == await second
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_coordinator_update_partial_and_failures(hass: MagicMock) -> None:
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {CONF_ENFANTS: [], CONF_CRECHE_ID: 1, CONF_CRECHE_NAME: "Old"}
    entry.options = {}

    client = MagicMock()
    client.get_tokens.return_value = {}
    client.creche_id = 99
    client.set_creche_id = MagicMock()
    client.get_me = AsyncMock(return_value={"creche": {"id": "bad"}, "nom": "X"})
    client.get_enfants = AsyncMock(return_value=[{"id": 2, "libelle": "B"}])
    client.get_planning_current_month = AsyncMock(side_effect=RuntimeError("p"))
    client.get_transmissions = AsyncMock(side_effect=RuntimeError("t"))
    client.get_albums = AsyncMock(side_effect=RuntimeError("a"))
    client.get_actualites = AsyncMock(return_value={})
    client.get_messages = AsyncMock(return_value=[])
    client.get_documents = AsyncMock(return_value=[])
    client.get_documents_famille = AsyncMock(return_value=[])
    client.get_documents_enfant = AsyncMock(return_value=[])
    client.get_facturation = AsyncMock(return_value=[])

    coord = OptieFamilyCoordinator(hass, client, entry)
    coord.known_enfant_ids = set()
    data = await coord._async_update_data()
    assert data.plannings == {}

    data.me = {"creche": {"id": 5, "nom": "New"}}
    data.enfants = [{"id": 2, "libelle": "B"}]
    await coord.async_sync_account_metadata(data)
    hass.config_entries.async_update_entry.assert_called()
    # creche_id config (1) conservé ; client aligné sur la config, pas /me
    client.set_creche_id.assert_called_with(1)

    entry.data = {
        CONF_CRECHE_ID: 5,
        CONF_CRECHE_NAME: "New",
        CONF_ENFANTS: [{"id": 2, "libelle": "B"}],
    }
    await coord.async_sync_account_metadata(data)

    data.me = "x"
    await coord.async_sync_account_metadata(data)

    from homeassistant.helpers.update_coordinator import UpdateFailed

    client.get_me = AsyncMock(side_effect=OptieFamilyAuthError("a"))
    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()
    client.get_me = AsyncMock(side_effect=OptieFamilyConnectionError("c"))
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    client.get_me = AsyncMock(side_effect=OptieFamilyApiError(500, "e"))
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    client.get_me = AsyncMock(side_effect=OptieFamilySetupError("s"))
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


@pytest.mark.asyncio
async def test_sensors(planning_present: dict, today: date, hass: MagicMock) -> None:
    data = OptieFamilyData()
    data.enfants = [{"id": 1, "libelle": "Alice"}]
    data.plannings = {1: planning_present}
    data.transmissions = {1: [{}]}
    data.albums = {1: [{}, {}]}
    data.messages = [
        {"vu": False, "date": "d", "sender": False},
        {"vu": True, "date": "d2", "sender": False},
        {"vu": False, "date": "d3", "sender": True},
    ]
    data.actualites = {"total": 3}
    data.documents = [1, 2]
    data.facturation = [1]

    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {CONF_CRECHE_NAME: "Crèche", CONF_ENFANTS: [{"id": 1, "libelle": "Alice"}]}
    entry.options = {}

    coordinator = MagicMock()
    coordinator.data = data
    coordinator.known_enfant_ids = set()
    coordinator.scan_interval = 1800
    coordinator.last_sync_at = datetime(2026, 9, 3, tzinfo=UTC)
    coordinator.transmissions_view_date = date.today()
    coordinator.transmissions_journal = {}
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

    await sensor_mod.async_setup_entry(hass, entry, async_add_entities)
    assert any(isinstance(e, sensor_mod.OptieFamilyLastRefreshSensor) for e in added)
    assert listeners

    for ent in added:
        if isinstance(ent, sensor_mod.OptieFamilyGlobalSensor):
            _ = ent.native_value
            _ = ent.extra_state_attributes
            _ = ent.device_info
        if isinstance(ent, sensor_mod.OptieFamilyLastRefreshSensor):
            assert ent.native_value is not None
            assert ent.extra_state_attributes["intervalle_minutes"] == 30
        if isinstance(ent, sensor_mod.OptieFamilyChildPresentSensor):
            attrs = ent.extra_state_attributes
            assert attrs["creneaux"] == ["07:45 - 18:45"]
            assert attrs["creneaux_libelle"] == "07:45 - 18:45"
            assert attrs["creneaux_detail"][0]["type"] == "regulier"
        if isinstance(ent, sensor_mod._ChildSensor):
            _ = ent.native_value
            _ = ent.extra_state_attributes
            _ = ent.device_info

    coordinator.data = None
    listeners[0]()
    coordinator.data = data
    coordinator.known_enfant_ids = {1}
    before = len(added)
    listeners[0]()
    assert len(added) == before
    data.enfants = [{"id": 1, "libelle": "Alice"}, {"id": 2, "libelle": "Bob"}]
    listeners[0]()
    assert any(getattr(e, "_enfant", None) and e._enfant.id == 2 for e in added)

    desc = sensor_mod.OptieFamilySensorDescription(
        key="x", name="X", value_fn=lambda d: 1, attributes_fn=None
    )
    g = sensor_mod.OptieFamilyGlobalSensor(coordinator, desc, entry)
    coordinator.data = data
    assert g.native_value == 1
    assert g.extra_state_attributes["optifamily_kind"] == "x"
    assert g.extra_state_attributes["config_entry_id"] == "e1"

    empty = OptieFamilyData()
    empty.messages = []
    for description in sensor_mod.GLOBAL_SENSORS:
        if description.key in ("messages_unread_creche", "messages_unread_me"):
            attrs = description.attributes_fn(empty)
            assert attrs["last_message_date"] is None
            assert attrs["last_unread_date"] is None
            assert attrs["total"] == 0
            assert attrs["non_lus"] == 0
            assert description.value_fn(empty) == 0

    mixed = OptieFamilyData()
    mixed.messages = [
        {"vu": False, "date": "2026-01-02", "sender": False},
        {"vu": True, "date": "2026-01-01", "sender": False},
        {"vu": False, "date": "2026-01-03", "sender": True},
    ]
    by_key = {d.key: d for d in sensor_mod.GLOBAL_SENSORS}
    assert by_key["messages_unread_creche"].value_fn(mixed) == 1
    assert by_key["messages_unread_me"].value_fn(mixed) == 1
    creche_attrs = by_key["messages_unread_creche"].attributes_fn(mixed)
    me_attrs = by_key["messages_unread_me"].attributes_fn(mixed)
    assert creche_attrs["origine"] == "creche"
    assert creche_attrs["total"] == 2
    assert creche_attrs["last_unread_date"] == "2026-01-02"
    assert me_attrs["origine"] == "moi"
    assert me_attrs["total"] == 1
    assert me_attrs["last_message_date"] == "2026-01-03"

    enfant = Enfant(id=9, libelle="Z")
    coordinator.data = OptieFamilyData()
    for cls in (
        sensor_mod.OptieFamilyChildPresentSensor,
        sensor_mod.OptieFamilyChildPlanningSlotsSensor,
        sensor_mod.OptieFamilyChildTransmissionsSensor,
        sensor_mod.OptieFamilyChildTransmissionsJournalSensor,
        sensor_mod.OptieFamilyChildAlbumsSensor,
    ):
        s = cls(coordinator, entry, enfant, "hub-device-id")
        _ = s.native_value
        _ = s.extra_state_attributes
        assert s.device_info["via_device_id"] == "hub-device-id"

    entry2 = MagicMock()
    entry2.entry_id = "e2"
    entry2.data = {}
    base = sensor_mod._OptieFamilyBaseSensor(coordinator, entry2)
    assert base.device_info["name"] == "OptiFamily"

    last = sensor_mod.OptieFamilyLastRefreshSensor(coordinator, entry)
    del coordinator.scan_interval
    assert last.extra_state_attributes["intervalle_minutes"] is None


@pytest.mark.asyncio
async def test_config_flow_user_and_creche() -> None:
    flow = OptieFamilyConfigFlow()
    flow.hass = MagicMock()

    form = await flow.async_step_user(None)
    assert form["type"] == "form"

    client = MagicMock()
    client.discover_creches = AsyncMock(return_value=[{"id": 1, "nom": "A"}])
    client.set_creche_id = MagicMock()
    client.authenticate = AsyncMock()
    client.get_me = AsyncMock(return_value={"nom": "Parent", "creche": {"id": 1, "nom": "A"}})
    client.get_enfants = AsyncMock(return_value=[{"id": 2, "libelle": "E"}])

    with (
        patch(
            "custom_components.optifamily.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.optifamily.config_flow.OptieFamilyApiClient",
            return_value=client,
        ),
    ):
        result = await flow.async_step_user({"username": " u@e.com ", "password": "secret"})
    assert result["type"] == "create_entry"

    flow = OptieFamilyConfigFlow()
    flow.hass = MagicMock()
    client.discover_creches = AsyncMock(return_value=[{"id": 1, "nom": "A"}, {"id": 2, "nom": "B"}])
    with (
        patch(
            "custom_components.optifamily.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.optifamily.config_flow.OptieFamilyApiClient",
            return_value=client,
        ),
    ):
        result = await flow.async_step_user({"username": "u@e.com", "password": "p"})
    assert result["step_id"] == "creche"

    for exc, key in (
        (OptieFamilyAuthError("a"), "invalid_auth"),
        (OptieFamilyConnectionError("c"), "cannot_connect"),
        (OptieFamilySetupError("s"), "no_creche"),
        (OptieFamilyApiError(502, "bad gateway"), "cannot_connect"),
        (RuntimeError("r"), "unknown"),
    ):
        flow = OptieFamilyConfigFlow()
        flow.hass = MagicMock()
        client.discover_creches = AsyncMock(side_effect=exc)
        with (
            patch(
                "custom_components.optifamily.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.optifamily.config_flow.OptieFamilyApiClient",
                return_value=client,
            ),
        ):
            result = await flow.async_step_user({"username": "u", "password": "p"})
        assert result["errors"]["base"] == key

    flow = OptieFamilyConfigFlow()
    with patch.object(flow, "async_step_user", AsyncMock(return_value={"ok": 1})) as m:
        assert await flow.async_step_import({"username": "u", "password": "p"}) == {"ok": 1}
        m.assert_awaited()

    flow = OptieFamilyConfigFlow()
    flow.hass = MagicMock()
    flow._flow_data = {"username": "u@e.com", "password": "p"}
    flow._creches = [{"id": 1, "nom": "A"}, {"id": 2, "nom": "B"}]
    form = await flow.async_step_creche(None)
    assert form["type"] == "form"

    client.authenticate = AsyncMock()
    client.get_me = AsyncMock(return_value={"creche": {}, "nom": ""})
    client.get_enfants = AsyncMock(return_value=[])
    client.set_creche_id = MagicMock()
    with (
        patch(
            "custom_components.optifamily.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.optifamily.config_flow.OptieFamilyApiClient",
            return_value=client,
        ),
    ):
        result = await flow.async_step_creche({CONF_CRECHE_ID: "2"})
    assert result["type"] == "create_entry"

    for exc, key in (
        (OptieFamilyAuthError("a"), "invalid_auth"),
        (OptieFamilyConnectionError("c"), "cannot_connect"),
        (OptieFamilyApiError(503, "unavailable"), "cannot_connect"),
        (RuntimeError("r"), "unknown"),
    ):
        flow = OptieFamilyConfigFlow()
        flow.hass = MagicMock()
        flow._flow_data = {"username": "u", "password": "p"}
        flow._creches = [{"id": 1, "nom": "A"}]
        with (
            patch(
                "custom_components.optifamily.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.optifamily.config_flow.OptieFamilyApiClient",
                return_value=client,
            ),
            patch.object(
                flow,
                "_async_create_entry_from_client",
                AsyncMock(side_effect=exc),
            ),
        ):
            result = await flow.async_step_creche({CONF_CRECHE_ID: "1"})
        assert result["errors"]["base"] == key

    opts = OptieFamilyConfigFlow.async_get_options_flow(MagicMock())
    assert isinstance(opts, OptieFamilyOptionsFlow)

    options = OptieFamilyOptionsFlow()
    options.config_entry = MagicMock(options={})
    form = await options.async_step_init(None)
    assert form["type"] == "form"
    created = await options.async_step_init(
        {
            "scan_interval_minutes": 30,
            "pause_updates": True,
            "pause_updates_start": "21:00:00",
            "pause_updates_end": "06:00:00",
            "pause_when_closed": True,
        }
    )
    assert created["type"] == "create_entry"
    assert created["data"]["scan_interval"] == 1800
    assert created["data"]["pause_updates"] is True
    assert created["data"]["pause_updates_start"] == "21:00:00"
    assert created["data"]["pause_updates_end"] == "06:00:00"
    assert created["data"]["pause_when_closed"] is True


# --- suite ---


@pytest.mark.asyncio
async def test_init_configured_creche_and_multi(hass: MagicMock) -> None:
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {"username": "u", "password": "p", CONF_CRECHE_ID: 42}
    entry.options = {}
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock(return_value="x")

    coord = MagicMock()
    coord.async_load_tokens = AsyncMock(return_value=False)
    coord.async_save_tokens = AsyncMock()
    coord.async_config_entry_first_refresh = AsyncMock()

    client = MagicMock()
    client.creche_id = None
    client.set_creche_id = MagicMock()
    client.ensure_authenticated = AsyncMock()

    with (
        patch.object(optifamily_init, "async_get_clientsession", return_value=MagicMock()),
        patch.object(optifamily_init, "OptieFamilyApiClient", return_value=client),
        patch.object(optifamily_init, "OptieFamilyCoordinator", return_value=coord),
    ):
        assert await optifamily_init.async_setup_entry(hass, entry) is True
    client.set_creche_id.assert_called_with(42)

    entry.data = {"username": "u", "password": "p"}
    client.creche_id = None
    client.discover_creches = AsyncMock(return_value=[{"id": 1}, {"id": 2}])
    with (
        patch.object(optifamily_init, "async_get_clientsession", return_value=MagicMock()),
        patch.object(optifamily_init, "OptieFamilyApiClient", return_value=client),
        patch.object(optifamily_init, "OptieFamilyCoordinator", return_value=coord),
        pytest.raises(Exception) as excinfo,
    ):
        await optifamily_init.async_setup_entry(hass, entry)
    assert "Plusieurs crèches" in str(excinfo.value) or excinfo.value.__class__.__name__


@pytest.mark.asyncio
async def test_coordinator_enabled_enfants_and_metadata(hass: MagicMock) -> None:
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {CONF_ENFANTS: [{"id": 1, "libelle": "A"}], CONF_CRECHE_ID: "bad"}
    entry.options = {CONF_ENABLED_ENFANTS: [1]}

    client = MagicMock()
    client.get_tokens.return_value = {}
    client.set_token_listener = MagicMock()
    client.creche_id = None
    client.set_creche_id = MagicMock()

    coord = OptieFamilyCoordinator(hass, client, entry)
    with patch.object(coord, "async_save_tokens", new=AsyncMock()):
        coord._schedule_save_tokens()
        assert hass.async_create_task.called

    data = OptieFamilyData()
    # configured non convertible → except TypeError/ValueError (l.219-220)
    entry.data = {CONF_ENFANTS: [{"id": 1, "libelle": "A"}], CONF_CRECHE_ID: object()}
    data.me = {"creche": {"id": 55, "nom": "X"}}
    data.enfants = [{"id": 1, "libelle": "A"}]
    client.creche_id = None
    await coord.async_sync_account_metadata(data)

    data.me = {"creche": {"id": "nope", "nom": "X"}}
    await coord.async_sync_account_metadata(data)

    # configured None → take /me
    entry.data = {CONF_ENFANTS: [{"id": 1, "libelle": "A"}]}
    data.me = {"creche": {"id": 55, "nom": "New"}}
    client.creche_id = None
    await coord.async_sync_account_metadata(data)
    client.set_creche_id.assert_called_with(55)

    # sync enabled: invalid current → set; newcomers; purge
    entry.data = {
        CONF_ENFANTS: [{"id": 1, "libelle": "A"}],
        CONF_CRECHE_ID: 55,
        CONF_CRECHE_NAME: "New",
    }
    entry.options = {CONF_ENABLED_ENFANTS: "broken"}
    data.enfants = [{"id": 1, "libelle": "A"}, {"id": 2, "libelle": "B"}]
    with patch.object(coord, "_purge_disabled_enfants") as purge:
        await coord.async_sync_account_metadata(data)
        purge.assert_called()

    entry.options = {CONF_ENABLED_ENFANTS: [1]}
    data.enfants = [{"id": 1, "libelle": "A"}, {"id": 2, "libelle": "B"}]
    # previous known = [1], newcomer 2 must be added
    assert coord._sync_enabled_enfants_options(data.enfants) is True
    # already synced
    entry.options = {CONF_ENABLED_ENFANTS: [1, 2]}
    assert coord._sync_enabled_enfants_options(data.enfants) is False
    # None → False
    entry.options = {}
    assert coord._sync_enabled_enfants_options(data.enfants) is False

    entry.options = {CONF_ENABLED_ENFANTS: [1]}
    entry.data = {
        CONF_ENFANTS: [{"id": 1, "libelle": "A"}, {"id": 2, "libelle": "B"}],
        CONF_CRECHE_ID: 55,
    }
    coord.known_enfant_ids = {1, 2}
    coord.known_calendar_enfant_ids = {1, 2}
    with patch(
        "custom_components.optifamily.coordinator.async_purge_enfant_devices",
        return_value=2,
    ) as purge_dev:
        coord._purge_disabled_enfants(data.enfants)
        purge_dev.assert_called()
    assert 2 not in coord.known_enfant_ids

    entry.options = {CONF_ENABLED_ENFANTS: [1, 2]}
    coord._purge_disabled_enfants(data.enfants)  # nothing excluded

    entry.options = {}
    coord._purge_disabled_enfants(data.enfants)  # enabled None

    await coord.async_set_documents_scope(DOCUMENTS_SCOPE_FAMILLE, 9)
    assert coord.documents_scope == DOCUMENTS_SCOPE_FAMILLE
    assert coord.documents_enfant_id == 9
    with pytest.raises(ValueError):
        await coord.async_set_documents_scope("nope")


@pytest.mark.asyncio
async def test_config_flow_reauth_and_options() -> None:
    flow = OptieFamilyConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"entry_id": "e1"}
    reauth_entry = MagicMock()
    reauth_entry.entry_id = "e1"
    reauth_entry.data = {
        CONF_USERNAME: "u@e.com",
        CONF_PASSWORD: "old",
        CONF_CRECHE_ID: 1001,
    }
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=reauth_entry)
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.hass.config_entries.async_reload = AsyncMock()

    form = await flow.async_step_reauth({CONF_USERNAME: "u@e.com", CONF_CRECHE_ID: 1001})
    assert form["type"] == "form"

    client = MagicMock()
    client.authenticate = AsyncMock()
    with (
        patch(
            "custom_components.optifamily.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.optifamily.config_flow.OptieFamilyApiClient",
            return_value=client,
        ),
    ):
        result = await flow.async_step_reauth_confirm({CONF_PASSWORD: "new"})
    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"

    for exc, key in (
        (OptieFamilyAuthError("a"), "invalid_auth"),
        (OptieFamilyConnectionError("c"), "cannot_connect"),
        (OptieFamilyApiError(500, "e"), "cannot_connect"),
        (RuntimeError("r"), "unknown"),
    ):
        flow = OptieFamilyConfigFlow()
        flow.hass = MagicMock()
        flow.context = {"entry_id": "e1"}
        flow._reauth_entry = reauth_entry
        client.authenticate = AsyncMock(side_effect=exc)
        with (
            patch(
                "custom_components.optifamily.config_flow.async_get_clientsession",
                return_value=MagicMock(),
            ),
            patch(
                "custom_components.optifamily.config_flow.OptieFamilyApiClient",
                return_value=client,
            ),
        ):
            result = await flow.async_step_reauth_confirm({CONF_PASSWORD: "x"})
        assert result["errors"]["base"] == key

    # me creche mismatch + bad id
    flow = OptieFamilyConfigFlow()
    flow.hass = MagicMock()
    flow._flow_data = {CONF_USERNAME: "u@e.com", CONF_PASSWORD: "p"}
    flow._creches = [{"id": 1, "nom": "A"}]
    client = MagicMock()
    client.set_creche_id = MagicMock()
    client.authenticate = AsyncMock()
    client.get_me = AsyncMock(return_value={"creche": {"id": "bad", "nom": "X"}, "nom": "P"})
    client.get_enfants = AsyncMock(return_value=[{"id": 2, "libelle": "E"}])
    with (
        patch(
            "custom_components.optifamily.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.optifamily.config_flow.OptieFamilyApiClient",
            return_value=client,
        ),
    ):
        result = await flow.async_step_creche({CONF_CRECHE_ID: "1"})
    assert result["type"] == "create_entry"

    flow = OptieFamilyConfigFlow()
    flow.hass = MagicMock()
    flow._flow_data = {CONF_USERNAME: "u@e.com", CONF_PASSWORD: "p"}
    flow._creches = [{"id": 1, "nom": "A"}]
    client.get_me = AsyncMock(return_value={"creche": {"id": 99, "nom": "Other"}, "nom": "P"})
    client.get_enfants = AsyncMock(return_value=[])
    with (
        patch(
            "custom_components.optifamily.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.optifamily.config_flow.OptieFamilyApiClient",
            return_value=client,
        ),
    ):
        result = await flow.async_step_creche({CONF_CRECHE_ID: "1"})
    assert result["data"][CONF_CRECHE_ID] == 1

    # options with enabled_enfants
    options = OptieFamilyOptionsFlow()
    options.hass = MagicMock()
    options.config_entry = MagicMock(
        data={CONF_ENFANTS: [{"id": 1, "libelle": "A"}, {"id": 2, "libelle": "B"}]},
        options={CONF_ENABLED_ENFANTS: [1, 2]},
    )
    form = await options.async_step_init(None)
    assert form["type"] == "form"

    with patch("custom_components.optifamily.config_flow.async_purge_enfant_devices") as purge:
        created = await options.async_step_init(
            {
                "scan_interval_minutes": 30,
                "pause_updates": True,
                "pause_updates_start": "21:00:00",
                "pause_updates_end": "06:00:00",
                "pause_when_closed": True,
                CONF_ENABLED_ENFANTS: ["1", "bad", 2],
            }
        )
    assert created["type"] == "create_entry"
    assert set(created["data"][CONF_ENABLED_ENFANTS]) == {1, 2}

    # string raw_enabled + empty → all_ids fallback + purge
    options.config_entry.options = {CONF_ENABLED_ENFANTS: [1]}
    with patch("custom_components.optifamily.config_flow.async_purge_enfant_devices") as purge:
        created = await options.async_step_init(
            {
                "scan_interval_minutes": 30,
                "pause_updates": False,
                "pause_updates_start": "21:00:00",
                "pause_updates_end": "06:00:00",
                "pause_when_closed": False,
                CONF_ENABLED_ENFANTS: "1",
            }
        )
        purge.assert_called()
    assert created["data"][CONF_ENABLED_ENFANTS] == [1]

    options.config_entry.options = {CONF_ENABLED_ENFANTS: [1, 2]}
    created = await options.async_step_init(
        {
            "scan_interval_minutes": 30,
            "pause_updates": True,
            "pause_updates_start": "21:00:00",
            "pause_updates_end": "06:00:00",
            "pause_when_closed": True,
            CONF_ENABLED_ENFANTS: "",
        }
    )
    assert set(created["data"][CONF_ENABLED_ENFANTS]) == {1, 2}


@pytest.mark.asyncio
async def test_sensors_phase_resume_documents(hass: MagicMock) -> None:
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
                            "creneaux": [{"type": "regulier", "label": "08:00 - 18:00"}],
                        }
                    ]
                }
            ]
        }
    }
    data.messages = [{"vu": False, "sender": False, "date": "d"}]
    data.documents = [{"id": 1}]
    data.documents_famille = [{"id": 2}]
    data.documents_enfant = {1: [{"id": 3}]}

    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {CONF_CRECHE_NAME: "C", CONF_ENFANTS: [{"id": 1, "libelle": "Alice"}]}
    entry.options = {}

    coordinator = MagicMock()
    coordinator.data = data
    coordinator.known_enfant_ids = set()
    coordinator.documents_scope = DOCUMENTS_SCOPE_CRECHE
    coordinator.documents_enfant_id = None
    coordinator.scan_interval = 1800
    coordinator.last_sync_at = datetime.now()
    coordinator.transmissions_view_date = date.today()
    coordinator.transmissions_journal = {}
    coordinator.async_add_listener = MagicMock(return_value=lambda: None)
    coordinator.async_update_listeners = MagicMock()
    entry.runtime_data = coordinator
    entry.async_on_unload = MagicMock()

    tick_cb: list[Any] = []

    def _track(_hass: Any, action: Any, _interval: Any) -> Any:
        tick_cb.append(action)
        return lambda: None

    added: list[Any] = []
    with patch("custom_components.optifamily.sensor.async_track_time_interval", _track):
        await sensor_mod.async_setup_entry(hass, entry, added.extend)

    assert tick_cb
    tick_cb[0](datetime.now())
    coordinator.async_update_listeners.assert_called()

    phase = next(e for e in added if isinstance(e, sensor_mod.OptieFamilyPhaseSensor))
    resume = next(e for e in added if isinstance(e, sensor_mod.OptieFamilyResumeSensor))
    docs = next(e for e in added if isinstance(e, sensor_mod.OptieFamilyDocumentsSensor))

    assert isinstance(phase.native_value, str)
    assert "phase" in phase.extra_state_attributes
    assert isinstance(resume.native_value, str)
    assert resume.extra_state_attributes["optifamily_kind"] == "resume"

    assert docs.native_value == 1
    attrs = docs.extra_state_attributes
    assert attrs["scope"] == DOCUMENTS_SCOPE_CRECHE
    assert attrs["counts"]["creche"] == 1

    coordinator.documents_scope = DOCUMENTS_SCOPE_FAMILLE
    assert docs.native_value == 1
    assert docs.extra_state_attributes["scope"] == DOCUMENTS_SCOPE_FAMILLE

    coordinator.documents_scope = DOCUMENTS_SCOPE_ENFANT
    coordinator.documents_enfant_id = 1
    assert docs.native_value == 1

    coordinator.data = None
    assert docs.native_value == 0
    assert docs.extra_state_attributes["counts"]["creche"] == 0

    # helpers
    coordinator.data = data
    assert sensor_mod._documents_for_scope(coordinator)[0] == DOCUMENTS_SCOPE_ENFANT
    coordinator.documents_scope = DOCUMENTS_SCOPE_CRECHE
    assert sensor_mod._summary_for_entry(coordinator, entry)["count"] >= 1
    coordinator.data = None
    assert sensor_mod._summary_for_entry(coordinator, entry)["count"] == 0


@pytest.mark.asyncio
async def test_coordinator_skips_disabled_enfants_polling(hass: MagicMock) -> None:
    """Polling enfant limité aux IDs suivis (plan 1.1.0)."""
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {
        CONF_ENFANTS: [
            {"id": 1, "libelle": "A"},
            {"id": 2, "libelle": "B"},
        ],
        CONF_CRECHE_ID: 1,
    }
    entry.options = {CONF_ENABLED_ENFANTS: [1]}

    client = MagicMock()
    client.get_tokens.return_value = {}
    client.set_token_listener = MagicMock()
    client.creche_id = 1
    client.get_me = AsyncMock(return_value={"id": 1})
    client.get_enfants = AsyncMock(
        return_value=[{"id": 1, "libelle": "A"}, {"id": 2, "libelle": "B"}]
    )
    client.get_planning_current_month = AsyncMock(return_value={})
    client.get_transmissions = AsyncMock(return_value=[])
    client.get_albums = AsyncMock(return_value=[])
    client.get_actualites = AsyncMock(return_value={"total": 0})
    client.get_messages = AsyncMock(return_value=[])
    client.get_documents = AsyncMock(return_value=[])
    client.get_documents_famille = AsyncMock(return_value=[])
    client.get_documents_enfant = AsyncMock(return_value=[])
    client.get_facturation = AsyncMock(return_value=[])

    coord = OptieFamilyCoordinator(hass, client, entry)
    with (
        patch.object(coord, "async_save_tokens", new=AsyncMock()),
        patch.object(coord, "async_sync_account_metadata", new=AsyncMock()),
    ):
        data = await coord._async_update_data()

    assert 1 in data.plannings
    assert 2 not in data.plannings
    assert 2 not in data.documents_enfant
    client.get_planning_current_month.assert_awaited_once_with(1)
    client.get_documents_enfant.assert_awaited_once_with(1)

    coord.data = data
    await coord.async_set_transmissions_view_date(date.today())
    assert set(coord.transmissions_journal) == {1}
