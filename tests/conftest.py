"""Fixtures partagées pour les tests OptiFamily."""

from __future__ import annotations

from datetime import date
import sys
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stubs Home Assistant : permettent de tester api/models sans installer HA.
# Doit rester avant tout import de custom_components.optifamily.
# ---------------------------------------------------------------------------


def _ensure_ha_stubs() -> None:
    if "homeassistant" in sys.modules and not isinstance(sys.modules["homeassistant"], MagicMock):
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
        "homeassistant.components",
        "homeassistant.components.sensor",
    ]
    for name in modules:
        if name not in sys.modules:
            sys.modules[name] = MagicMock()

    # Modules réellement utilisés par api/models (pas de stub nécessaire),
    # mais __init__.py tire config.py → voluptuous.
    if "voluptuous" not in sys.modules:
        vol = ModuleType("voluptuous")
        vol.Schema = MagicMock()  # type: ignore[attr-defined]
        vol.Required = MagicMock()  # type: ignore[attr-defined]
        vol.Optional = MagicMock()  # type: ignore[attr-defined]
        vol.ALLOW_EXTRA = object()  # type: ignore[attr-defined]
        sys.modules["voluptuous"] = vol


_ensure_ha_stubs()

import aiohttp  # noqa: E402
import pytest  # noqa: E402

from custom_components.optifamily.api import OptieFamilyApiClient  # noqa: E402


@pytest.fixture
def today() -> date:
    return date(2026, 9, 3)


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
        facturation=[],
    )
