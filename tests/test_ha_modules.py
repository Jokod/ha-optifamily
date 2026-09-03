"""Couverture exceptions, models, config, init, coordinator, sensor, config_flow."""

from __future__ import annotations

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
    CONF_ENFANTS,
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


@pytest.mark.asyncio
async def test_unload_remove_reload(hass: MagicMock) -> None:
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.runtime_data = MagicMock()
    entry.runtime_data.client.logout = AsyncMock()
    entry.runtime_data.async_clear_tokens = AsyncMock()

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
    client.get_facturation = AsyncMock(return_value=[])

    coord = OptieFamilyCoordinator(hass, client, entry)
    coord.known_enfant_ids = set()
    data = await coord._async_update_data()
    assert data.plannings == {}

    data.me = {"creche": {"id": 5, "nom": "New"}}
    data.enfants = [{"id": 2, "libelle": "B"}]
    await coord.async_sync_account_metadata(data)
    hass.config_entries.async_update_entry.assert_called()
    client.set_creche_id.assert_called_with(5)

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
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    client.get_me = AsyncMock(side_effect=OptieFamilyConnectionError("c"))
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()
    client.get_me = AsyncMock(side_effect=OptieFamilyApiError(500, "e"))
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


@pytest.mark.asyncio
async def test_sensors(planning_present: dict, today: date, hass: MagicMock) -> None:
    data = OptieFamilyData()
    data.enfants = [{"id": 1, "libelle": "Alice"}]
    data.plannings = {1: planning_present}
    data.transmissions = {1: [{}]}
    data.albums = {1: [{}, {}]}
    data.messages = [{"vu": False, "date": "d"}, {"vu": True, "date": "d2"}]
    data.actualites = {"total": 3}
    data.documents = [1, 2]
    data.facturation = [1]

    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {CONF_CRECHE_NAME: "Crèche", CONF_ENFANTS: [{"id": 1, "libelle": "Alice"}]}

    coordinator = MagicMock()
    coordinator.data = data
    coordinator.known_enfant_ids = set()
    coordinator.scan_interval = 1800
    coordinator.last_update_success = datetime(2026, 9, 3, tzinfo=UTC)
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
    assert g.extra_state_attributes is None

    empty = OptieFamilyData()
    empty.messages = []
    for description in sensor_mod.GLOBAL_SENSORS:
        if description.key == "messages_unread":
            assert description.attributes_fn(empty)["last_message_date"] is None

    enfant = Enfant(id=9, libelle="Z")
    coordinator.data = OptieFamilyData()
    for cls in (
        sensor_mod.OptieFamilyChildPresentSensor,
        sensor_mod.OptieFamilyChildPlanningSlotsSensor,
        sensor_mod.OptieFamilyChildTransmissionsSensor,
        sensor_mod.OptieFamilyChildAlbumsSensor,
    ):
        s = cls(coordinator, entry, enfant)
        _ = s.native_value
        _ = s.extra_state_attributes

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
    created = await options.async_step_init({"scan_interval_minutes": 30})
    assert created["type"] == "create_entry"
    assert created["data"]["scan_interval"] == 1800
