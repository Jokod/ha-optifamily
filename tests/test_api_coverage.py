"""Couverture API : chemins restants."""

from __future__ import annotations

from datetime import date
from typing import Any

import aiohttp
from aioresponses import aioresponses
import pytest

from custom_components.optifamily.api import (
    OptieFamilyApiClient,
    _as_dict,
    _as_list,
    _error_detail,
    _normalize_creche,
    _parse_creches_from_response,
    normalize_enfants,
)
from custom_components.optifamily.const import API_BASE_URL
from custom_components.optifamily.exceptions import (
    OptieFamilyApiError,
    OptieFamilyAuthError,
    OptieFamilyConnectionError,
    OptieFamilySetupError,
)


def _url(path: str) -> str:
    return f"{API_BASE_URL}{path}"


def test_normalize_creche_edges() -> None:
    assert _normalize_creche("x") is None
    assert _normalize_creche({}) is None
    assert _normalize_creche({"id": "bad"}) is None
    assert _normalize_creche({"crecheId": 9}) == {"id": 9, "nom": "Crèche 9"}
    assert _normalize_creche({"id": 1, "nom": "A"}) == {"id": 1, "nom": "A"}


def test_parse_creches_dict_variants() -> None:
    assert _parse_creches_from_response({"creches": [{"id": 1, "nom": "A"}]}) == [
        {"id": 1, "nom": "A"}
    ]
    assert _parse_creches_from_response({"structures": [{"id": 2, "label": "B"}]}) == [
        {"id": 2, "nom": "B"}
    ]
    assert _parse_creches_from_response({"data": [{"id": 3, "libelle": "C"}]}) == [
        {"id": 3, "nom": "C"}
    ]
    assert _parse_creches_from_response({"creche": {"id": 4, "nom": "D"}}) == [
        {"id": 4, "nom": "D"}
    ]
    assert _parse_creches_from_response({"crecheId": 5, "nom": "E"}) == [{"id": 5, "nom": "E"}]
    # dedupe
    assert (
        len(
            _parse_creches_from_response(
                {"creches": [{"id": 1, "nom": "A"}, {"id": 1, "nom": "A2"}]}
            )
        )
        == 1
    )


def test_normalize_enfants_default_label() -> None:
    assert normalize_enfants([{"id": 7}]) == [{"id": 7, "libelle": "Enfant 7"}]
    assert normalize_enfants([{"id": object()}]) == []


@pytest.mark.asyncio
async def test_discover_creches_empty_raises(api_client: OptieFamilyApiClient) -> None:
    with aioresponses() as mocked:
        mocked.post(_url("/auth/pre-login"), payload=[])
        with pytest.raises(OptieFamilySetupError):
            await api_client.discover_creches()


@pytest.mark.asyncio
async def test_authenticate_discovers_creche(session, login_response: dict[str, Any]) -> None:
    client = OptieFamilyApiClient("u@e.com", "p", session, creche_id=None)
    with aioresponses() as mocked:
        mocked.post(_url("/auth/pre-login"), payload=[{"id": 1001, "libelle": "A"}])
        mocked.post(_url("/auth/pre-login"), payload=[{"id": 1001, "libelle": "A"}])
        mocked.post(_url("/auth/login"), payload=login_response)
        await client.authenticate()
    assert client.creche_id == 1001
    assert client.is_authenticated


@pytest.mark.asyncio
async def test_ensure_authenticated_short_circuit(api_client: OptieFamilyApiClient) -> None:
    api_client.set_tokens("A", "R")
    await api_client.ensure_authenticated()
    assert api_client.get_tokens()["access_token"] == "A"


@pytest.mark.asyncio
async def test_ensure_authenticated_refresh_fails_then_login(
    api_client: OptieFamilyApiClient, login_response: dict[str, Any]
) -> None:
    api_client._access_token = None
    api_client._refresh_token = "BAD"
    with aioresponses() as mocked:
        mocked.post(_url("/auth/refresh"), status=401, body="no")
        mocked.post(_url("/auth/pre-login"), payload=[{"id": 1001, "libelle": "A"}])
        mocked.post(_url("/auth/login"), payload=login_response)
        await api_client.ensure_authenticated()
    assert api_client.is_authenticated


@pytest.mark.asyncio
async def test_apply_login_invalid(api_client: OptieFamilyApiClient) -> None:
    with pytest.raises(OptieFamilyAuthError):
        api_client._apply_login_response([])
    with pytest.raises(OptieFamilyAuthError):
        api_client._apply_login_response({})


@pytest.mark.asyncio
async def test_creche_id_property(api_client: OptieFamilyApiClient) -> None:
    assert api_client.creche_id == 1001
    api_client.set_creche_id(2002)
    assert api_client.creche_id == 2002


@pytest.mark.asyncio
async def test_logout_swallows_errors(api_client: OptieFamilyApiClient) -> None:
    api_client.set_tokens("A", "R")
    with aioresponses() as mocked:
        mocked.get(_url("/api/auth/v3/logout"), exception=ConnectionError("boom"))
        await api_client.logout()
    assert not api_client.is_authenticated


@pytest.mark.asyncio
async def test_endpoints(api_client: OptieFamilyApiClient) -> None:
    api_client.set_tokens("A", "R")
    with aioresponses() as mocked:
        mocked.get(_url("/api/auth/v3/me"), payload={"nom": "X"})
        mocked.get(
            _url("/api/auth/v3/opti-family/enfant/2001/planning/2026/9"),
            payload={"label": "P"},
        )
        mocked.get(
            _url("/api/auth/v3/opti-family/enfant/2001/transmissions/2026-09-03"),
            payload=[{"id": 1}],
        )
        mocked.get(
            _url("/api/auth/v3/opti-family/enfant/2001/albums"),
            payload=[{"id": 1}],
        )
        mocked.get(
            _url("/api/auth/v3/opti-family/actualites/from/0/to/20"),
            payload={"total": 1},
        )
        mocked.get(
            _url("/api/auth/v3/opti-family/documents/creche/1001"),
            payload=[{"id": 1}],
        )
        mocked.get(_url("/api/auth/v3/opti-family/facturation"), payload=[])

        assert (await api_client.get_me())["nom"] == "X"
        assert (await api_client.get_planning(2001, 2026, 9))["label"] == "P"
        assert len(await api_client.get_transmissions(2001, date(2026, 9, 3))) == 1
        assert len(await api_client.get_albums(2001)) == 1
        assert (await api_client.get_actualites())["total"] == 1
        assert len(await api_client.get_documents()) == 1
        assert await api_client.get_facturation() == []


@pytest.mark.asyncio
async def test_get_planning_current_month(api_client: OptieFamilyApiClient) -> None:
    api_client.set_tokens("A", "R")
    now = date.today()
    path = f"/api/auth/v3/opti-family/enfant/1/planning/{now.year}/{now.month}"
    with aioresponses() as mocked:
        mocked.get(_url(path), payload={"ok": True})
        assert (await api_client.get_planning_current_month(1))["ok"] is True


@pytest.mark.asyncio
async def test_get_documents_without_creche(session) -> None:
    client = OptieFamilyApiClient("u", "p", session, creche_id=None)
    client.set_tokens("A", "R")
    with pytest.raises(OptieFamilySetupError):
        await client.get_documents()


@pytest.mark.asyncio
async def test_request_errors(api_client: OptieFamilyApiClient) -> None:
    api_client.set_tokens("A", "R")
    with aioresponses() as mocked:
        mocked.get(_url("/api/auth/v3/me"), status=500, body="fail-body")
        with pytest.raises(OptieFamilyApiError) as err:
            await api_client.get_me()
        assert err.value.status == 500

    with aioresponses() as mocked:
        mocked.get(_url("/api/auth/v3/me"), status=204, body="")
        assert await api_client.get_me() == {}

    with aioresponses() as mocked:
        mocked.get(_url("/api/auth/v3/me"), status=200, body="{not-json")
        with pytest.raises(OptieFamilyApiError):
            await api_client.get_me()

    with aioresponses() as mocked:
        mocked.get(_url("/api/auth/v3/me"), exception=aiohttp.ClientConnectionError())
        with pytest.raises(OptieFamilyConnectionError):
            await api_client.get_me()

    with aioresponses() as mocked:
        mocked.get(_url("/api/auth/v3/me"), exception=aiohttp.ServerTimeoutError())
        with pytest.raises(OptieFamilyConnectionError):
            await api_client.get_me()

    with aioresponses() as mocked:
        mocked.get(_url("/api/auth/v3/me"), status=403, body="forbidden")
        with pytest.raises(OptieFamilyAuthError, match="Accès refusé"):
            await api_client.get_me()

    with aioresponses() as mocked:
        mocked.get(
            _url("/api/auth/v3/me"),
            status=400,
            body='{"status":400,"message":"Required request body is missing"}',
        )
        with pytest.raises(OptieFamilyApiError, match="Required request body"):
            await api_client.get_me()

    with aioresponses() as mocked:
        mocked.get(_url("/api/auth/v3/me"), exception=aiohttp.ClientError())
        with pytest.raises(OptieFamilyConnectionError, match="Erreur réseau"):
            await api_client.get_me()


def test_response_shape_and_error_detail() -> None:
    assert _as_list(None) == []
    assert _as_list([1]) == [1]
    assert _as_list({"enfants": [{"id": 1}]}) == [{"id": 1}]
    assert _as_list({"x": 1}) == []
    assert _as_dict(None) == {}
    assert _as_dict({"a": 1}) == {"a": 1}
    assert _error_detail(400, "") == "HTTP 400"
    assert _error_detail(400, '{"message":"oops"}') == "oops"
    assert _error_detail(500, '{"error":"boom"}') == "boom"
    assert _error_detail(502, '{"foo":1}') == '{"foo":1}'
    assert _error_detail(500, "plain") == "plain"
    assert _error_detail(500, "[1]") == "[1]"


@pytest.mark.asyncio
async def test_request_401_final(api_client: OptieFamilyApiClient) -> None:
    api_client.set_tokens("A", "R")
    with aioresponses() as mocked:
        mocked.get(_url("/api/auth/v3/me"), status=401, body="x")
        mocked.post(_url("/auth/refresh"), status=401, body="x")
        mocked.post(_url("/auth/pre-login"), payload=[{"id": 1001, "libelle": "A"}])
        mocked.post(_url("/auth/login"), status=401, body="bad")
        with pytest.raises(OptieFamilyAuthError):
            await api_client.get_me()


@pytest.mark.asyncio
async def test_request_authenticates_when_needed(session) -> None:
    client = OptieFamilyApiClient("u@e.com", "p", session, creche_id=1001)
    with aioresponses() as mocked:
        mocked.post(_url("/auth/pre-login"), payload=[{"id": 1001, "libelle": "A"}])
        mocked.post(
            _url("/auth/login"),
            payload={"accessToken": "A", "refreshToken": "R"},
        )
        mocked.get(_url("/api/auth/v3/me"), payload={"ok": 1})
        assert (await client.get_me())["ok"] == 1


@pytest.mark.asyncio
async def test_request_server_timeout(api_client: OptieFamilyApiClient) -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    api_client.set_tokens("A", "R")
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(side_effect=aiohttp.ServerTimeoutError())
    cm.__aexit__ = AsyncMock(return_value=False)
    with (
        patch.object(api_client._session, "request", return_value=cm),
        pytest.raises(OptieFamilyConnectionError, match="Timeout"),
    ):
        await api_client.get_me()
