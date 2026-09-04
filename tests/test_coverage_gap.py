"""Compléter la couverture 100 % (nouveautés transmissions / pause / services)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from aioresponses import aioresponses
import pytest

from custom_components.optifamily import services as services_mod
from custom_components.optifamily.api import OptieFamilyApiClient
from custom_components.optifamily.const import (
    CONF_ENFANTS,
    CONF_PAUSE_UPDATES,
    CONF_PAUSE_WHEN_CLOSED,
    DOMAIN,
    is_update_paused,
    parse_clock,
)
from custom_components.optifamily.coordinator import (
    OptieFamilyCoordinator,
    OptieFamilyData,
    _famille_id_from_me,
    _PlanningCacheEntry,
)
from custom_components.optifamily.exceptions import OptieFamilyApiError
from custom_components.optifamily.models import (
    _transmission_chips,
    _transmission_detail_text,
    _transmission_display_time,
    _transmission_title,
    format_minutes_clock,
    normalize_transmission,
    normalize_transmissions,
    transmissions_markdown,
)
from tests.test_api_coverage import _url


def test_parse_clock_fallbacks() -> None:
    assert parse_clock("nope", "08:30:00") == (8, 30, 0)
    assert parse_clock("25:00:00", "07:00:00") == (7, 0, 0)
    assert parse_clock("12", "00:00:00") == (12, 0, 0)
    assert is_update_paused(12 * 3600, enabled=True, start="12:00:00", end="12:00:00") is False


def test_famille_id_from_me_branches() -> None:
    assert _famille_id_from_me(None) is None
    assert _famille_id_from_me({}) is None
    assert _famille_id_from_me({"famille": {"id": 74501}}) == 74501
    assert _famille_id_from_me({"familleId": "abc"}) is None
    assert _famille_id_from_me({"id": 9}) == 9


def test_planning_cache_freshness() -> None:
    ok = _PlanningCacheEntry({"a": 1}, ok=True)
    assert ok.is_fresh() is True
    bad = _PlanningCacheEntry({}, ok=False)
    bad.fetched_at -= 10_000
    assert bad.is_fresh() is False


def test_transmission_edge_cases() -> None:
    assert format_minutes_clock(-1) is None
    assert format_minutes_clock(24 * 60) is None
    assert format_minutes_clock("x") is None
    assert normalize_transmission("x") is None  # type: ignore[arg-type]
    assert normalize_transmissions([{"heure": object()}])[0]["sort_key"] == 0

    depart = {
        "type": "depart",
        "detail": "18:30",
        "valeur1": "1110",
        "heure": "1200",
    }
    assert _transmission_display_time(depart) == "18:30"
    assert _transmission_detail_text(depart) == ""

    depart2 = {
        "type": "depart",
        "detail": "au revoir",
        "valeur1": "1110",
        "heure": "1200",
    }
    assert _transmission_display_time(depart2) == "18:30"
    assert _transmission_detail_text(depart2) == "au revoir"

    assert (
        _transmission_title({"type": "activite", "sousType": "peinture"}) == "Activité · peinture"
    )
    assert _transmission_title({"type": "", "sousType": ""}) == "Transmission"
    assert (
        _transmission_detail_text({"type": "change", "valeur1": "Non défini", "detail": "ok"})
        == "ok"
    )
    assert _transmission_detail_text({"type": "repas", "valeur1": "150", "detail": ""}) == "150 ml"
    assert _transmission_detail_text({"type": "note", "valeur1": "x", "detail": ""}) == "x"
    assert (
        _transmission_display_time({"type": "arrivee", "valeur1": "480", "detail": ""}) == "08:00"
    )
    assert _transmission_display_time({"type": "sieste", "heure": "", "valeur1": "600"}) == "10:00"
    md = transmissions_markdown(
        [{"type": "note", "heure": "100", "detail": 'a <b> & "c"', "complements": ""}]
    )
    assert "Note" in md
    assert 'a <b> & "c"' in md
    assert _transmission_chips(
        [
            {"label": "Note", "value": "x", "kind": "note"},
            {"label": "Heure", "value": "", "kind": "badge"},
            {"label": "", "value": "ok", "kind": "badge"},
            {"label": "Propreté", "value": "Couche", "kind": "chip"},
        ]
    ) == [
        {"content": "ok", "tone": "info"},
        {"content": "Couche", "tone": "success"},
    ]


@pytest.mark.asyncio
async def test_api_documents_famille_enfant(api_client: OptieFamilyApiClient) -> None:
    api_client.set_tokens("A", "R")
    with aioresponses() as mocked:
        mocked.get(
            _url("/api/auth/v3/opti-family/documents/famille/74501"),
            payload=[{"id": 1}],
        )
        mocked.get(
            _url("/api/auth/v3/opti-family/documents/enfant/82518"),
            payload=[{"id": 2}],
        )
        assert len(await api_client.get_documents_famille(74501)) == 1
        assert len(await api_client.get_documents_enfant(82518)) == 1


@pytest.mark.asyncio
async def test_coordinator_pause_and_journal(hass: MagicMock) -> None:
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {CONF_ENFANTS: [{"id": 1, "libelle": "A"}]}
    entry.options = {CONF_PAUSE_UPDATES: "true"}

    client = MagicMock()
    client.get_tokens.return_value = {}
    client.get_me = AsyncMock(return_value={"id": 74501})
    client.get_enfants = AsyncMock(return_value=[{"id": 1, "libelle": "A"}])
    client.get_planning_current_month = AsyncMock(return_value={"semaines": []})
    client.get_transmissions = AsyncMock(return_value=[{"id": 1, "type": "note", "heure": "100"}])
    client.get_albums = AsyncMock(return_value=[])
    client.get_actualites = AsyncMock(return_value={})
    client.get_messages = AsyncMock(return_value=[])
    client.get_documents = AsyncMock(return_value=[{"id": "c"}])
    client.get_documents_famille = AsyncMock(return_value=[{"id": "f"}])
    client.get_documents_enfant = AsyncMock(return_value=[{"id": "e"}])
    client.get_facturation = AsyncMock(return_value=[])

    coord = OptieFamilyCoordinator(hass, client, entry)
    data = await coord._async_update_data()
    assert data.documents_famille
    assert data.documents_enfant[1]
    assert 1 in coord.transmissions_journal

    coord.data = data
    with patch.object(coord, "_is_in_pause_window", return_value=True):
        paused = await coord._async_update_data()
    assert paused is data
    client.get_me.assert_awaited_once()

    # Pause crèche fermée (aucun créneau) — conserve le cache
    closed_day = date.today().isoformat()
    data.plannings = {
        1: {"semaines": [{"journees": [{"date": closed_day, "creneaux": [{"type": "fermeture"}]}]}]}
    }
    coord.data = data
    with patch.object(coord, "_is_in_pause_window", return_value=False):
        paused_closed = await coord._async_update_data()
        assert paused_closed is data
        assert client.get_me.await_count == 1
        assert coord._pause_reason() == "crèche fermée / aucun créneau aujourd'hui"

        coord.entry.options = {CONF_PAUSE_WHEN_CLOSED: "0"}
        assert coord._is_creche_closed_pause() is False
        coord.entry.options = {CONF_PAUSE_WHEN_CLOSED: "yes"}
        saved = coord.data
        coord.data = None
        assert coord._is_creche_closed_pause() is False
        coord.data = saved
        coord.entry.options = {CONF_PAUSE_WHEN_CLOSED: True}

        # Réactive le polling (créneau régulier) pour la suite des tests
        data.plannings = {
            1: {
                "semaines": [
                    {
                        "journees": [
                            {
                                "date": closed_day,
                                "creneaux": [{"type": "regulier", "label": "08:00 - 18:00"}],
                            }
                        ]
                    }
                ]
            }
        }
        coord.data = data
        assert coord._pause_reason() is None

    client.get_documents_famille = AsyncMock(side_effect=RuntimeError("f"))
    client.get_documents_enfant = AsyncMock(side_effect=RuntimeError("e"))
    client.get_me = AsyncMock(return_value={"famille": {"id": 1}})
    with patch.object(coord, "_is_in_pause_window", return_value=False):
        await coord._async_update_data()

    client.get_transmissions = AsyncMock(side_effect=RuntimeError("t"))
    day = date.today() - timedelta(days=1)
    coord.data = OptieFamilyData()
    coord.data.enfants = [{"id": 1, "libelle": "A"}, {"bad": True}, {"id": "x"}]
    await coord.async_set_transmissions_view_date(day)
    assert coord.transmissions_view_date == day
    assert coord.transmissions_journal[1] == []

    coord.data = None
    entry.data = {CONF_ENFANTS: [{"id": 1, "libelle": "A"}]}
    client.get_transmissions = AsyncMock(return_value=[{"id": 9}])
    await coord.async_set_transmissions_view_date(day)
    assert coord.transmissions_journal[1] == [{"id": 9}]

    # data.enfants vide → fallback CONF_ENFANTS
    coord.data = OptieFamilyData()
    await coord.async_set_transmissions_view_date(day)
    assert 1 in coord.transmissions_journal

    shifted = await coord.async_shift_transmissions_view_date(1)
    assert shifted == day + timedelta(days=1)


def test_is_in_pause_window_string_and_import_fallback(hass: MagicMock) -> None:
    entry = MagicMock()
    entry.options = {
        CONF_PAUSE_UPDATES: "yes",
        "pause_updates_start": "00:00:00",
        "pause_updates_end": "23:59:59",
    }
    client = MagicMock()
    coord = OptieFamilyCoordinator(hass, client, entry)

    fake_dt = MagicMock()
    fake_dt.now.return_value = datetime(2026, 9, 4, 12, 0, 0)
    fake_util = MagicMock()
    fake_util.dt = fake_dt
    with patch.dict(
        "sys.modules", {"homeassistant.util": fake_util, "homeassistant.util.dt": fake_dt}
    ):
        assert coord._is_in_pause_window() is True
        fake_dt.now.assert_called()

    import builtins

    real_import = builtins.__import__

    def _import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name in {"homeassistant.util", "homeassistant.util.dt"} or name.startswith(
            "homeassistant.util."
        ):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_import):
        assert coord._is_in_pause_window() is True

    entry.options = {CONF_PAUSE_UPDATES: "0"}
    assert coord._is_in_pause_window() is False


@pytest.mark.asyncio
async def test_services_set_shift_and_unload(hass: MagicMock) -> None:
    hass.services.has_service = MagicMock(side_effect=[False, True, True, True, True])
    services_mod.async_setup_services(hass)
    assert hass.services.async_register.call_count == 4
    services_mod.async_setup_services(hass)  # already registered

    coord = MagicMock(spec=OptieFamilyCoordinator)
    coord.async_set_transmissions_view_date = AsyncMock()
    coord.async_shift_transmissions_view_date = AsyncMock()
    coord.async_set_documents_scope = AsyncMock()
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.runtime_data = coord
    other = MagicMock()
    other.entry_id = "skip"
    other.runtime_data = SimpleNamespace()
    hass.config_entries.async_entries = MagicMock(return_value=[entry, other])

    call = MagicMock()
    call.hass = hass
    call.data = {"date": datetime(2026, 9, 1, 10, 0, 0), "config_entry_id": "e1"}
    await services_mod._async_set_date(call)
    coord.async_set_transmissions_view_date.assert_awaited()

    call.data = {"date": date(2026, 9, 2)}
    await services_mod._async_set_date(call)

    call.data = {"date": "2026-09-03"}
    await services_mod._async_set_date(call)

    call.data = {"days": -1, "config_entry_id": "e1"}
    await services_mod._async_shift_date(call)
    coord.async_shift_transmissions_view_date.assert_awaited_with(-1)

    call.data = {"scope": "famille", "config_entry_id": "e1"}
    await services_mod._async_set_documents_scope(call)
    coord.async_set_documents_scope.assert_awaited()

    hass.config_entries.async_entries = MagicMock(return_value=[])
    await services_mod._async_set_date(MagicMock(hass=hass, data={"date": "2026-01-01"}))
    await services_mod._async_shift_date(MagicMock(hass=hass, data={"days": 1}))
    await services_mod._async_set_documents_scope(MagicMock(hass=hass, data={"scope": "creche"}))

    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    services_mod.async_unload_services(hass)
    hass.services.async_remove.assert_not_called()

    hass.config_entries.async_entries = MagicMock(return_value=[])
    hass.services.has_service = MagicMock(return_value=True)
    services_mod.async_unload_services(hass)
    assert hass.services.async_remove.call_count == 4


def test_parse_day_helpers() -> None:
    assert services_mod._parse_day(date(2026, 1, 2)) == date(2026, 1, 2)
    assert services_mod._parse_day(datetime(2026, 1, 2, 8, 0)) == date(2026, 1, 2)
    assert services_mod._parse_day("2026-01-03T12:00:00") == date(2026, 1, 3)


# --- tests issus de la répartition domain-based ---


@pytest.mark.asyncio
async def test_services_download_paths(hass: MagicMock, tmp_path: Path) -> None:
    hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
    hass.bus.async_fire = MagicMock()

    data = OptieFamilyData()
    data.documents = [{"id": "d1", "download_url": "https://ex/d1.pdf"}]
    data.documents_famille = [{"id": "f1", "url": "https://ex/f1.pdf"}]
    data.documents_enfant = {1: [{"id": "e1", "path": "/files/e1.pdf"}]}
    data.facturation = [{"id": "bill1", "fileUrl": "https://ex/bill.pdf"}]
    data.albums = {
        1: [
            {
                "id": "alb1",
                "photos": [{"id": "ph1", "mediaUrl": "https://ex/p1.jpg"}],
            },
            "skip",
            {"id": "alb2", "medias": [{"id": "ph2", "url": "https://ex/p2.jpg"}]},
        ]
    }

    coord = MagicMock(spec=OptieFamilyCoordinator)
    coord.data = data
    coord.client = MagicMock()
    coord.client.download_bytes = AsyncMock(return_value=b"BYTES")

    entry = MagicMock()
    entry.entry_id = "e1"
    entry.runtime_data = coord
    hass.config_entries.async_entries = MagicMock(return_value=[entry])

    call = MagicMock()
    call.hass = hass

    # no targets
    hass.config_entries.async_entries = MagicMock(return_value=[])
    call.data = {"kind": "document", "id": "d1"}
    await services_mod._async_download(call)
    hass.bus.async_fire.assert_not_called()

    hass.config_entries.async_entries = MagicMock(return_value=[entry])

    # document by id
    call.data = {"kind": "document", "id": "d1", "config_entry_id": "e1"}
    await services_mod._async_download(call)
    assert any(c.args[0] == f"{DOMAIN}_download_ready" for c in hass.bus.async_fire.call_args_list)

    # facture
    call.data = {"kind": "facture", "id": "bill1"}
    await services_mod._async_download(call)

    # photo by photo id + enfant
    call.data = {"kind": "photo", "id": "ph1", "enfant_id": 1}
    await services_mod._async_download(call)

    # photo album id without enfant (flat search)
    call.data = {"kind": "photo", "id": "alb1"}
    await services_mod._async_download(call)

    # photo not found
    call.data = {"kind": "photo", "id": "missing"}
    await services_mod._async_download(call)
    assert any(
        c.args[0] == f"{DOMAIN}_download_failed" and c.args[1]["reason"] == "not_downloadable"
        for c in hass.bus.async_fire.call_args_list
    )

    # explicit url
    call.data = {"kind": "document", "id": "x", "download_url": "https://ex/x.bin"}
    await services_mod._async_download(call)

    # download API error
    coord.client.download_bytes = AsyncMock(side_effect=OptieFamilyApiError(500, "fail"))
    call.data = {"kind": "document", "id": "d1"}
    await services_mod._async_download(call)

    # no data
    coord.data = None
    call.data = {"kind": "document", "id": "d1"}
    await services_mod._async_download(call)

    # find candidate branches
    coord.data = data
    assert (
        services_mod._find_download_candidate(coord, kind="document", item_id="f1", enfant_id=None)
        is not None
    )
    assert (
        services_mod._find_download_candidate(coord, kind="document", item_id="e1", enfant_id=None)
        is not None
    )
    assert (
        services_mod._find_download_candidate(coord, kind="photo", item_id="ph2", enfant_id=None)
        is not None
    )
    assert (
        services_mod._find_download_candidate(coord, kind="photo", item_id="no", enfant_id=99)
        is None
    )
    assert (
        services_mod._find_download_candidate(coord, kind="facture", item_id="no", enfant_id=None)
        is None
    )
