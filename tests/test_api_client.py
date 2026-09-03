"""Tests fonctionnels — client API (HTTP mocké)."""

from __future__ import annotations

from typing import Any

from aioresponses import aioresponses
import pytest

from custom_components.optifamily.api import OptieFamilyApiClient
from custom_components.optifamily.const import API_BASE_URL
from custom_components.optifamily.exceptions import OptieFamilyAuthError


def _url(path: str) -> str:
    return f"{API_BASE_URL}{path}"


@pytest.mark.asyncio
async def test_discover_creches(
    api_client: OptieFamilyApiClient,
) -> None:
    with aioresponses() as mocked:
        mocked.post(
            _url("/auth/pre-login"),
            payload=[{"id": 1001, "libelle": "Crèche A"}],
        )
        creches = await api_client.discover_creches()
    assert creches == [{"id": 1001, "nom": "Crèche A"}]


@pytest.mark.asyncio
async def test_authenticate_login_flow(
    api_client: OptieFamilyApiClient,
    login_response: dict[str, Any],
) -> None:
    with aioresponses() as mocked:
        mocked.post(_url("/auth/pre-login"), payload=[{"id": 1001, "libelle": "A"}])
        mocked.post(_url("/auth/login"), payload=login_response)
        await api_client.authenticate()

    assert api_client.is_authenticated
    tokens = api_client.get_tokens()
    assert tokens["access_token"] == "ACCESS_TOKEN"
    assert tokens["refresh_token"] == "REFRESH_TOKEN"


@pytest.mark.asyncio
async def test_refresh_tokens(
    api_client: OptieFamilyApiClient,
) -> None:
    api_client.set_tokens("OLD_ACCESS", "REFRESH_TOKEN")
    with aioresponses() as mocked:
        mocked.post(
            _url("/auth/refresh"),
            payload={
                "accessToken": "NEW_ACCESS",
                "refreshToken": "NEW_REFRESH",
            },
        )
        await api_client.refresh_tokens()

    tokens = api_client.get_tokens()
    assert tokens["access_token"] == "NEW_ACCESS"
    assert tokens["refresh_token"] == "NEW_REFRESH"


@pytest.mark.asyncio
async def test_refresh_without_token_raises(
    api_client: OptieFamilyApiClient,
) -> None:
    with pytest.raises(OptieFamilyAuthError):
        await api_client.refresh_tokens()


@pytest.mark.asyncio
async def test_ensure_authenticated_uses_refresh(
    api_client: OptieFamilyApiClient,
) -> None:
    api_client._access_token = None
    api_client._refresh_token = "REFRESH_TOKEN"

    with aioresponses() as mocked:
        mocked.post(
            _url("/auth/refresh"),
            payload={"accessToken": "FROM_REFRESH", "refreshToken": "REFRESH_TOKEN"},
        )
        await api_client.ensure_authenticated()

    assert api_client.get_tokens()["access_token"] == "FROM_REFRESH"


@pytest.mark.asyncio
async def test_get_enfants_authenticated(
    api_client: OptieFamilyApiClient,
) -> None:
    api_client.set_tokens("ACCESS_TOKEN", "REFRESH_TOKEN")
    with aioresponses() as mocked:
        mocked.get(
            _url("/api/auth/v3/opti-family/enfants"),
            payload=[{"id": 2001, "libelle": "Alice"}],
        )
        enfants = await api_client.get_enfants()
    assert enfants == [{"id": 2001, "libelle": "Alice"}]


@pytest.mark.asyncio
async def test_401_triggers_refresh_then_retry(
    api_client: OptieFamilyApiClient,
) -> None:
    api_client.set_tokens("EXPIRED", "REFRESH_TOKEN")
    with aioresponses() as mocked:
        mocked.get(
            _url("/api/auth/v3/opti-family/messages"),
            status=401,
            body="unauthorized",
        )
        mocked.post(
            _url("/auth/refresh"),
            payload={"accessToken": "NEW", "refreshToken": "REFRESH_TOKEN"},
        )
        mocked.get(
            _url("/api/auth/v3/opti-family/messages"),
            payload=[{"id": 1, "sender": True, "message": "Hi", "date": "x", "vu": False}],
        )
        messages = await api_client.get_messages()

    assert len(messages) == 1
    assert api_client.get_tokens()["access_token"] == "NEW"


@pytest.mark.asyncio
async def test_logout_empty_body(
    api_client: OptieFamilyApiClient,
) -> None:
    api_client.set_tokens("ACCESS_TOKEN", "REFRESH_TOKEN")
    with aioresponses() as mocked:
        mocked.get(_url("/api/auth/v3/logout"), status=200, body="")
        await api_client.logout()
    assert not api_client.is_authenticated
