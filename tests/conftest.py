"""Fixtures partagées pour les tests OptiFamily."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import sys
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Stubs Home Assistant : permettent de tester sans installer HA.
# Doit rester avant tout import de custom_components.optifamily.
# ---------------------------------------------------------------------------


def _ensure_ha_stubs() -> None:
    if getattr(_ensure_ha_stubs, "_done", False):
        return

    modules = [
        "homeassistant",
        "homeassistant.config_entries",
        "homeassistant.core",
        "homeassistant.exceptions",
        "homeassistant.const",
        "homeassistant.helpers",
        "homeassistant.helpers.aiohttp_client",
        "homeassistant.helpers.storage",
        "homeassistant.helpers.update_coordinator",
        "homeassistant.helpers.entity",
        "homeassistant.helpers.entity_platform",
        "homeassistant.helpers.selector",
        "homeassistant.helpers.typing",
        "homeassistant.helpers.device_registry",
        "homeassistant.helpers.config_validation",
        "homeassistant.components",
        "homeassistant.components.sensor",
        "homeassistant.components.calendar",
    ]
    for name in modules:
        sys.modules.setdefault(name, ModuleType(name))

    @dataclass(frozen=True)
    class _SensorEntityDescription:
        key: str = ""
        name: str | None = None
        icon: str | None = None
        device_class: Any = None
        state_class: Any = None
        entity_category: Any = None
        native_unit_of_measurement: str | None = None

    class _SensorEntity:
        _attr_has_entity_name = False

    class _CoordinatorEntity:
        def __class_getitem__(cls, _item: Any) -> type:
            return cls

        def __init__(self, coordinator: Any) -> None:
            self.coordinator = coordinator

    class _SensorDeviceClass:
        TIMESTAMP = "timestamp"
        ENUM = "enum"

    class _SensorStateClass:
        MEASUREMENT = "measurement"

    class _EntityCategory:
        DIAGNOSTIC = "diagnostic"

    class _DataUpdateCoordinator:
        def __class_getitem__(cls, _item: Any) -> type:
            return cls

        def __init__(self, hass: Any, logger: Any, *args: Any, **kwargs: Any) -> None:
            self.hass = hass
            self.logger = logger
            self.name = kwargs.get("name")
            self.update_interval = kwargs.get("update_interval")
            self.data = None
            self.last_update_success = None

        async def async_config_entry_first_refresh(self) -> None:
            self.data = await self._async_update_data()

        async def _async_update_data(self) -> Any:
            raise NotImplementedError

        def async_add_listener(self, listener: Any) -> Any:
            return lambda: None

        def async_update_listeners(self) -> None:
            return None

    class _ConfigFlow:
        def __init_subclass__(cls, *, domain: str | None = None, **kwargs: Any) -> None:
            super().__init_subclass__(**kwargs)
            cls.DOMAIN = domain  # type: ignore[attr-defined]

        def __init__(self) -> None:
            self.hass = MagicMock()
            self.unique_id = None

        async def async_set_unique_id(self, unique_id: str) -> None:
            self.unique_id = unique_id

        def _abort_if_unique_id_configured(self) -> None:
            return None

        def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs: Any) -> dict[str, Any]:
            return {"type": "create_entry", **kwargs}

        def async_abort(self, **kwargs: Any) -> dict[str, Any]:
            return {"type": "abort", **kwargs}

    class _OptionsFlow:
        def __init__(self) -> None:
            self.config_entry = MagicMock(options={})

        def async_show_form(self, **kwargs: Any) -> dict[str, Any]:
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs: Any) -> dict[str, Any]:
            return {"type": "create_entry", **kwargs}

    class _ConfigEntryAuthFailed(Exception):
        pass

    class _ConfigEntryNotReady(Exception):
        pass

    class _Store:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.data: dict[str, Any] | None = None

        async def async_save(self, data: Any) -> None:
            self.data = data

        async def async_load(self) -> Any:
            return self.data

        async def async_remove(self) -> None:
            self.data = None

    def _callback(func: Any) -> Any:
        return func

    class _CalendarEntity:
        _attr_has_entity_name = False

    @dataclass
    class _CalendarEvent:
        start: Any
        end: Any
        summary: str
        description: str | None = None
        uid: str | None = None

    # sensor
    sensor_mod = sys.modules["homeassistant.components.sensor"]
    sensor_mod.SensorEntityDescription = _SensorEntityDescription
    sensor_mod.SensorEntity = _SensorEntity
    sensor_mod.SensorDeviceClass = _SensorDeviceClass
    sensor_mod.SensorStateClass = _SensorStateClass

    cal_mod = sys.modules["homeassistant.components.calendar"]
    cal_mod.CalendarEntity = _CalendarEntity
    cal_mod.CalendarEvent = _CalendarEvent

    # const
    const_mod = sys.modules["homeassistant.const"]
    const_mod.EntityCategory = _EntityCategory
    const_mod.CONF_PASSWORD = "password"
    const_mod.CONF_USERNAME = "username"

    # entity / coordinator / storage
    sys.modules["homeassistant.helpers.entity"].DeviceInfo = dict
    sys.modules["homeassistant.helpers.entity_platform"].AddEntitiesCallback = Any
    sys.modules["homeassistant.helpers.typing"].ConfigType = dict
    coord_mod = sys.modules["homeassistant.helpers.update_coordinator"]
    coord_mod.CoordinatorEntity = _CoordinatorEntity
    coord_mod.DataUpdateCoordinator = _DataUpdateCoordinator
    coord_mod.UpdateFailed = type("UpdateFailed", (Exception,), {})
    sys.modules["homeassistant.helpers.storage"].Store = _Store

    # config_entries / exceptions / core
    ce = sys.modules["homeassistant.config_entries"]
    ce.ConfigFlow = _ConfigFlow
    ce.OptionsFlow = _OptionsFlow
    ce.ConfigEntry = MagicMock
    ce.ConfigFlowResult = dict
    ce.SOURCE_IMPORT = "import"

    exc = sys.modules["homeassistant.exceptions"]
    exc.ConfigEntryAuthFailed = _ConfigEntryAuthFailed
    exc.ConfigEntryNotReady = _ConfigEntryNotReady

    core = sys.modules["homeassistant.core"]
    core.callback = _callback
    core.HomeAssistant = MagicMock
    core.ServiceCall = MagicMock

    # selectors : renvoyer des types voluptuous-compatibles
    sel = sys.modules["homeassistant.helpers.selector"]

    class _EnumNS:
        EMAIL = "email"
        PASSWORD = "password"
        DROPDOWN = "dropdown"
        SLIDER = "slider"
        TEXT = "text"

    def _text_selector(*args: Any, **kwargs: Any) -> type:
        return str

    def _number_selector(*args: Any, **kwargs: Any) -> type:
        return int

    def _select_selector(*args: Any, **kwargs: Any) -> type:
        return str

    class _Config:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    sel.TextSelector = _text_selector
    sel.NumberSelector = _number_selector
    sel.SelectSelector = _select_selector
    sel.BooleanSelector = lambda *args, **kwargs: bool
    sel.TimeSelector = lambda *args, **kwargs: str
    sel.TextSelectorConfig = _Config
    sel.NumberSelectorConfig = _Config
    sel.SelectSelectorConfig = _Config
    sel.NumberSelectorMode = _EnumNS
    sel.SelectSelectorMode = _EnumNS
    sel.TextSelectorType = _EnumNS

    # aiohttp_client
    sys.modules["homeassistant.helpers.aiohttp_client"].async_get_clientsession = MagicMock()

    # device_registry
    dr_mod = sys.modules["homeassistant.helpers.device_registry"]

    class _DeviceEntry:
        def __init__(self, device_id: str = "hub-device-id") -> None:
            self.id = device_id

    class _DeviceRegistry:
        def async_get_or_create(self, **kwargs: Any) -> _DeviceEntry:
            return _DeviceEntry()

    def _async_get_registry(_hass: Any) -> _DeviceRegistry:
        return _DeviceRegistry()

    dr_mod.async_get = _async_get_registry

    # config_validation (services)
    cv_mod = sys.modules["homeassistant.helpers.config_validation"]
    cv_mod.string = str
    cv_mod.date = lambda value: value

    # homeassistant root
    ha = sys.modules["homeassistant"]
    ha.config_entries = ce

    # voluptuous (installed or stub)
    try:
        import voluptuous  # noqa: F401
    except ImportError:
        vol = ModuleType("voluptuous")

        class _Schema:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def __call__(self, value: Any) -> Any:
                return value

        def _required(key: Any) -> Any:
            return key

        def _optional(key: Any) -> Any:
            return key

        vol.Schema = _Schema  # type: ignore[attr-defined]
        vol.Required = _required  # type: ignore[attr-defined]
        vol.Optional = _optional  # type: ignore[attr-defined]
        vol.ALLOW_EXTRA = object()  # type: ignore[attr-defined]
        sys.modules["voluptuous"] = vol

    _ensure_ha_stubs._done = True  # type: ignore[attr-defined]


_ensure_ha_stubs()

import aiohttp  # noqa: E402
import pytest  # noqa: E402

from custom_components.optifamily.api import OptieFamilyApiClient  # noqa: E402


@pytest.fixture
def today() -> date:
    return date.today()


@pytest.fixture
def planning_present(today: date) -> dict[str, Any]:
    return {
        "label": "Planning de septembre 2026",
        "previous": "2026-08",
        "next": "2026-10",
        "semaines": [
            {
                "numero": "S36",
                "journees": [
                    {
                        "label": "J 3",
                        "date": today.isoformat(),
                        "visible": True,
                        "canAdd": True,
                        "creneaux": [
                            {
                                "type": "regulier",
                                "id": 1,
                                "label": "07:45 - 18:45",
                                "details": "",
                                "editable": False,
                            }
                        ],
                    }
                ],
            }
        ],
    }


@pytest.fixture
def planning_absent(today: date) -> dict[str, Any]:
    return {
        "semaines": [
            {
                "journees": [
                    {
                        "date": today.isoformat(),
                        "creneaux": [
                            {
                                "type": "fermeture",
                                "id": 2,
                                "label": "Fermé",
                                "details": "",
                            }
                        ],
                    }
                ]
            }
        ]
    }


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as client_session:
        yield client_session


@pytest.fixture
def api_client(session: aiohttp.ClientSession) -> OptieFamilyApiClient:
    return OptieFamilyApiClient(
        username="parent@example.com",
        password="PASSWORD",
        session=session,
        creche_id=1001,
    )


@pytest.fixture
def login_response() -> dict[str, str]:
    return {
        "status": "success",
        "accessToken": "ACCESS_TOKEN",
        "refreshToken": "REFRESH_TOKEN",
    }


@pytest.fixture
def fake_data() -> SimpleNamespace:
    return SimpleNamespace(
        enfants=[],
        persisted_enfants=[],
        plannings={},
        transmissions={},
        albums={},
        messages=[],
        actualites={},
        documents=[],
        documents_famille=[],
        documents_enfant={},
        facturation=[],
    )


@pytest.fixture
def hass(tmp_path) -> MagicMock:
    mock = MagicMock()
    mock.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
    mock.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    mock.config_entries.async_reload = AsyncMock(return_value=None)
    mock.config_entries.async_entries = MagicMock(return_value=[])
    mock.async_create_task = MagicMock()
    mock.services.has_service = MagicMock(return_value=False)
    mock.services.async_register = MagicMock()
    mock.services.async_remove = MagicMock()
    mock.config_entries.flow.async_init = AsyncMock()
    mock.config.path = lambda *parts: str(tmp_path.joinpath(*parts))

    async def _add_executor_job(func: Any, *args: Any) -> Any:
        return func(*args)

    mock.async_add_executor_job = _add_executor_job
    return mock
