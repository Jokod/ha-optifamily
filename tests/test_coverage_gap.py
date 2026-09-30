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
    CONF_CRECHE_ID,
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
    assert (
        _transmission_detail_text(
            {"type": "repas", "sousType": "solide", "valeur1": "0", "detail": ""}
        )
        == ""
    )
    assert (
        _transmission_detail_text(
            {"type": "repas", "sousType": "biberon", "valeur1": "0", "detail": ""}
        )
        == ""
    )
    assert (
        _transmission_detail_text(
            {"type": "repas", "sousType": "biberon", "valeur1": "peu", "detail": ""}
        )
        == "peu"
    )
    assert _transmission_detail_text({"type": "note", "valeur1": "x", "detail": ""}) == "x"

    change_selles = normalize_transmission(
        {
            "heure": "700",
            "type": "change",
            "sousType": "couche",
            "valeur1": "caca",
            "valeur2": "Mou",
            "valeur3": "",
            "detail": "",
            "complements": "",
            "icon": "couche",
        }
    )
    assert change_selles is not None
    assert any(r.get("value") == "Mou" for r in change_selles["rows"])

    # pipi + type de selles renseigné → ignoré (pas pertinent)
    change_pipi = normalize_transmission(
        {
            "heure": "701",
            "type": "change",
            "sousType": "couche",
            "valeur1": "pipi",
            "valeur2": "Mou",
            "valeur3": "crème",
            "detail": "",
            "complements": "",
            "icon": "couche",
        }
    )
    assert change_pipi is not None
    assert not any(r.get("label") == "Type de selles" for r in change_pipi["rows"])
    assert any(r.get("label") == "Soin" and r.get("value") == "Crème" for r in change_pipi["rows"])

    from custom_components.optifamily.models import _api_defined, _repas_volume_label, _soin_label

    assert _api_defined(None) is False
    assert _api_defined(" Non défini ") is False
    assert _api_defined("non defini") is False
    assert _api_defined("Mou") is True
    assert _soin_label("creme") == "Crème"
    assert _soin_label("crème") == "Crème"
    assert _soin_label("talc") == "Talc"
    assert (
        _repas_volume_label({"sousType": "solide", "detail": "purée OK", "valeur1": "0"})
        == "purée OK"
    )
    assert (
        _transmission_display_time({"type": "arrivee", "valeur1": "480", "detail": ""}) == "08:00"
    )
    assert _transmission_display_time({"type": "sieste", "heure": "", "valeur1": "600"}) == "10:00"
    from custom_components.optifamily.models import aggregate_transmissions

    empty = aggregate_transmissions([])
    assert empty["total"] == 0
    assert empty["resume"] == "Aucune donnée agrégée"
    assert aggregate_transmissions(None)["total"] == 0
    assert aggregate_transmissions(["x"])["total"] == 0  # type: ignore[list-item]

    via_detail = aggregate_transmissions(
        [{"type": "repas", "sousType": "biberon", "detail": "120 ml", "valeur1": ""}]
    )
    assert via_detail["biberons"] == 1
    assert via_detail["biberons_ml"] == 120

    via_icon = aggregate_transmissions(
        [{"type": "repas", "icon": "biberon", "valeur1": "90", "detail": ""}]
    )
    assert via_icon["biberons_ml"] == 90

    no_volume = aggregate_transmissions(
        [{"type": "repas", "sousType": "biberon", "valeur1": "", "detail": "peu"}]
    )
    assert no_volume["biberons"] == 1
    assert no_volume["biberons_ml"] == 0

    sieste_bounds = aggregate_transmissions(
        [{"type": "sieste", "heure": "600", "valeur1": "660", "detail": ""}]
    )
    assert sieste_bounds["siestes_minutes"] == 60

    bad_duration = aggregate_transmissions(
        [{"type": "sieste", "heure": "x", "valeur1": "y", "detail": "99:99"}]
    )
    assert bad_duration["siestes"] == 1
    assert bad_duration["siestes_minutes"] == 0

    change_pipi = aggregate_transmissions(
        [{"type": "change", "valeur1": "pipi"}, {"type": "depart", "detail": "18:00"}]
    )
    assert change_pipi["changes_pipi"] == 1
    assert change_pipi["depart"] == "18:00"
    assert "pipi" in change_pipi["resume"]

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
    client.get_creche = AsyncMock(return_value={})
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

    # Infos crèche : échec API → dict vide, le reste continue
    client.get_creche = AsyncMock(side_effect=RuntimeError("creche down"))
    client.get_me = AsyncMock(return_value={"id": 74501, "famille": {"id": 1}})
    with (
        patch.object(coord, "_is_in_pause_window", return_value=False),
        patch.object(coord, "_is_creche_closed_pause", return_value=False),
    ):
        data2 = await coord._async_update_data()
    assert data2.creche == {}

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


@pytest.mark.asyncio
async def test_day_rollover_resets_journal_and_bypasses_pause(hass: MagicMock) -> None:
    """Au changement de jour civil, le journal revient à today même en pause."""
    entry = MagicMock()
    entry.entry_id = "entry-day"
    entry.data = {CONF_ENFANTS: [{"id": 1, "libelle": "A"}]}
    entry.options = {CONF_PAUSE_WHEN_CLOSED: False}
    client = MagicMock()
    client.get_me = AsyncMock(return_value={"id": 1})
    client.get_enfants = AsyncMock(return_value=[{"id": 1, "libelle": "A"}])
    client.get_planning_current_month = AsyncMock(return_value={"semaines": []})
    client.get_transmissions = AsyncMock(return_value=[{"id": "today"}])
    client.get_albums = AsyncMock(return_value=[])
    client.get_actualites = AsyncMock(return_value={})
    client.get_messages = AsyncMock(return_value=[])
    client.get_creche = AsyncMock(return_value={})
    client.get_documents = AsyncMock(return_value=[])
    client.get_documents_famille = AsyncMock(return_value=[])
    client.get_documents_enfant = AsyncMock(return_value=[])
    client.get_facturation = AsyncMock(return_value=[])

    coord = OptieFamilyCoordinator(hass, client, entry)
    yesterday = date.today() - timedelta(days=1)
    coord._data_day = yesterday
    coord.transmissions_view_date = yesterday
    coord.data = OptieFamilyData()

    with patch.object(coord, "_is_in_pause_window", return_value=True):
        data = await coord._async_update_data()

    assert coord.transmissions_view_date == date.today()
    assert coord._data_day == date.today()
    assert data.transmissions[1] == [{"id": "today"}]
    assert coord.transmissions_journal[1] == [{"id": "today"}]
    client.get_me.assert_awaited()


@pytest.mark.asyncio
async def test_force_refresh_bypasses_pause(hass: MagicMock) -> None:
    entry = MagicMock()
    entry.entry_id = "entry-force"
    entry.data = {CONF_ENFANTS: [{"id": 1, "libelle": "A"}]}
    entry.options = {CONF_PAUSE_WHEN_CLOSED: False}
    client = MagicMock()
    client.get_me = AsyncMock(return_value={"id": 1})
    client.get_enfants = AsyncMock(return_value=[{"id": 1, "libelle": "A"}])
    client.get_planning_current_month = AsyncMock(return_value={"semaines": []})
    client.get_transmissions = AsyncMock(return_value=[])
    client.get_albums = AsyncMock(return_value=[])
    client.get_actualites = AsyncMock(return_value={})
    client.get_messages = AsyncMock(return_value=[])
    client.get_creche = AsyncMock(return_value={})
    client.get_documents = AsyncMock(return_value=[])
    client.get_documents_famille = AsyncMock(return_value=[])
    client.get_documents_enfant = AsyncMock(return_value=[])
    client.get_facturation = AsyncMock(return_value=[])

    coord = OptieFamilyCoordinator(hass, client, entry)
    coord.data = OptieFamilyData()
    coord._data_day = date.today()
    with patch.object(coord, "_is_in_pause_window", return_value=True):
        paused = await coord._async_update_data()
        assert paused is coord.data
        assert client.get_me.await_count == 0

        await coord.async_request_sync()
        assert client.get_me.await_count == 1
        assert coord._force_refresh is False


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
    hass.services.has_service = MagicMock(side_effect=[False, True, True, True, True, True])
    services_mod.async_setup_services(hass)
    assert hass.services.async_register.call_count == 7
    services_mod.async_setup_services(hass)  # already registered

    coord = MagicMock(spec=OptieFamilyCoordinator)
    coord.async_set_transmissions_view_date = AsyncMock()
    coord.async_shift_transmissions_view_date = AsyncMock()
    coord.async_set_documents_scope = AsyncMock()
    coord.async_set_album = AsyncMock()
    coord.async_read_actualite = AsyncMock()
    coord.async_request_sync = AsyncMock()
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

    call.data = {}
    await services_mod._async_set_date(call)
    coord.async_set_transmissions_view_date.assert_awaited_with(date.today())

    call.data = {"days": -1, "config_entry_id": "e1"}
    await services_mod._async_shift_date(call)
    coord.async_shift_transmissions_view_date.assert_awaited_with(-1)

    call.data = {"scope": "famille", "config_entry_id": "e1"}
    await services_mod._async_set_documents_scope(call)
    coord.async_set_documents_scope.assert_awaited()

    call.data = {"enfant_id": 1, "album_id": 9668, "config_entry_id": "e1"}
    await services_mod._async_set_album(call)
    coord.async_set_album.assert_awaited_with(1, 9668)

    call.data = {"id": 49792, "config_entry_id": "e1"}
    await services_mod._async_read_actualite(call)
    coord.async_read_actualite.assert_awaited_with(49792)

    call.data = {"config_entry_id": "e1"}
    await services_mod._async_refresh(call)
    coord.async_request_sync.assert_awaited()

    hass.config_entries.async_entries = MagicMock(return_value=[])
    await services_mod._async_set_date(MagicMock(hass=hass, data={"date": "2026-01-01"}))
    await services_mod._async_shift_date(MagicMock(hass=hass, data={"days": 1}))
    await services_mod._async_set_documents_scope(MagicMock(hass=hass, data={"scope": "creche"}))
    await services_mod._async_set_album(MagicMock(hass=hass, data={"enfant_id": 1, "album_id": 1}))
    await services_mod._async_read_actualite(MagicMock(hass=hass, data={"id": 1}))
    await services_mod._async_refresh(MagicMock(hass=hass, data={}))

    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    services_mod.async_unload_services(hass)
    hass.services.async_remove.assert_not_called()

    hass.config_entries.async_entries = MagicMock(return_value=[])
    hass.services.has_service = MagicMock(return_value=True)
    services_mod.async_unload_services(hass)
    assert hass.services.async_remove.call_count == 7


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
                "photos": 1,
                "photo": {"id": "ph1"},
            },
            "skip",
            {"id": "alb2", "medias": [{"id": "ph2", "url": "https://ex/p2.jpg"}]},
        ]
    }
    coord = MagicMock(spec=OptieFamilyCoordinator)
    coord.data = data
    coord.client = MagicMock()
    coord.client.download_bytes = AsyncMock(return_value=b"\xff\xd8\xffBYTES")
    coord.album_photos_cache = {
        (1, 10): {"total": 1, "photos": [{"id": "ph_cached"}]},
    }
    coord.actualite_detail_cache = {}
    coord.photo_local_urls = {}
    coord.remember_photo_local_url = MagicMock()

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

    # photo by photo id + enfant (cover) → albums/
    call.data = {"kind": "photo", "id": "ph1", "enfant_id": 1, "source": "albums"}
    await services_mod._async_download(call)
    assert (tmp_path / "www" / "optifamily" / "albums" / "ph1.jpg").is_file()

    # photo from album photos cache
    call.data = {"kind": "photo", "id": "ph_cached", "enfant_id": 1}
    await services_mod._async_download(call)

    # photo id without candidate → construit /photo/{id}/photo (défaut albums)
    call.data = {"kind": "photo", "id": "orphan99"}
    await services_mod._async_download(call)

    # photo actualité → actualites/
    call.data = {"kind": "photo", "id": "act1", "source": "actualites"}
    await services_mod._async_download(call)
    assert (tmp_path / "www" / "optifamily" / "actualites" / "act1.jpg").is_file()

    # photo déjà en cache disque (albums)
    cached_file = tmp_path / "www" / "optifamily" / "albums" / "disk1.jpg"
    cached_file.parent.mkdir(parents=True, exist_ok=True)
    cached_file.write_bytes(b"JPEG")
    coord.client.download_bytes.reset_mock()
    call.data = {"kind": "photo", "id": "disk1", "source": "albums"}
    await services_mod._async_download(call)
    coord.client.download_bytes.assert_not_called()
    coord.remember_photo_local_url.assert_called()

    # document without url/media
    call.data = {"kind": "document", "id": "missing"}
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

    # find candidate branches (tuple item, source)
    coord.data = data
    assert (
        services_mod._find_download_candidate(coord, kind="document", item_id="f1", enfant_id=None)[
            0
        ]
        is not None
    )
    assert (
        services_mod._find_download_candidate(coord, kind="document", item_id="e1", enfant_id=None)[
            0
        ]
        is not None
    )
    item, src = services_mod._find_download_candidate(
        coord, kind="photo", item_id="ph2", enfant_id=None
    )
    assert item is not None and src == "albums"
    assert services_mod._find_download_candidate(
        coord, kind="photo", item_id="no", enfant_id=99
    ) == (None, None)
    assert services_mod._find_download_candidate(
        coord, kind="facture", item_id="no", enfant_id=None
    ) == (None, None)


@pytest.mark.asyncio
async def test_album_photos_cache_and_actualite_read(hass: MagicMock, tmp_path: Path) -> None:
    hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {CONF_ENFANTS: [{"id": 1, "libelle": "A"}]}
    entry.options = {}
    client = MagicMock()
    client.get_album_photos = AsyncMock(
        side_effect=[
            {"total": 3, "photos": [{"id": 1}, {"id": 2}]},
            {"total": 3, "photos": [{"id": 3}]},
        ]
    )
    client.get_actualite = AsyncMock(
        side_effect=[
            RuntimeError("boom"),
            {"id": 49792, "titre": "OK", "contenu": "x"},
        ]
    )
    coord = OptieFamilyCoordinator(hass, client, entry)
    coord.async_update_listeners = MagicMock()

    # Pagination : 2 appels pour total=3
    payload = await coord._ensure_album_photos(1, 9668)
    assert payload["total"] == 3
    assert [p["id"] for p in payload["photos"]] == [1, 2, 3]
    assert client.get_album_photos.await_count == 2

    # Cache hit : pas de nouvel appel
    again = await coord._ensure_album_photos(1, 9668)
    assert again is payload
    assert client.get_album_photos.await_count == 2

    # Échec : ne pas mettre en cache
    client.get_album_photos = AsyncMock(side_effect=RuntimeError("net"))
    failed = await coord._ensure_album_photos(1, 42)
    assert failed == {"total": 0, "photos": []}
    assert (1, 42) not in coord.album_photos_cache

    # Actualité : échec ne sélectionne pas
    assert await coord.async_read_actualite(49792) is None
    assert coord.selected_actualite_id is None
    assert 49792 not in coord.actualite_detail_cache

    # Succès puis cache (pas de 2e vue API)
    detail = await coord.async_read_actualite("49792")
    assert detail and detail["id"] == 49792
    assert coord.selected_actualite_id == 49792
    client.get_actualite.reset_mock()
    cached = await coord.async_read_actualite(49792)
    assert cached is detail
    client.get_actualite.assert_not_awaited()

    # Album disparu → désélection
    coord.selected_album[1] = 9668
    coord.album_photos_cache[(1, 9668)] = payload
    coord._invalidate_stale_album_photo_caches({1: [{"id": 99, "photos": 1}]})
    assert coord.selected_album[1] is None
    assert (1, 9668) not in coord.album_photos_cache

    # Compteur changé → invalide le cache
    coord.album_photos_cache[(1, 99)] = {"total": 1, "photos": [{"id": 1}]}
    coord._invalidate_stale_album_photo_caches({1: [{"id": 99, "photos": 5}]})
    assert (1, 99) not in coord.album_photos_cache

    # Hydrate URLs locales depuis le disque (dossiers séparés)
    www = tmp_path / "www" / "optifamily"
    (www / "albums").mkdir(parents=True)
    (www / "actualites").mkdir(parents=True)
    (www / "albums" / "2168059.jpg").write_bytes(b"JPEG")
    (www / "actualites" / "2168065.jpg").write_bytes(b"JPEG")
    coord.hydrate_photo_local_urls()
    assert coord.photo_local_urls["albums:2168059"] == "/local/optifamily/albums/2168059.jpg"
    assert (
        coord.photo_local_urls["actualites:2168065"] == "/local/optifamily/actualites/2168065.jpg"
    )


@pytest.mark.asyncio
async def test_album_actualite_coverage_edges(hass: MagicMock, tmp_path: Path) -> None:
    """Branches albums/actualités/photos restantes pour 100 % couverture."""
    hass.config.path = lambda *parts: str(tmp_path.joinpath(*parts))
    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {CONF_ENFANTS: [{"id": 1, "libelle": "A"}]}
    entry.options = {}
    client = MagicMock()
    # Pages de 36 jusqu'à dépasser le garde-fou offset>500
    client.get_album_photos = AsyncMock(
        side_effect=lambda _e, _a, offset, _to: {
            "total": 600,
            "photos": [{"id": offset + i} for i in range(36)],
        }
    )
    client.get_actualite = AsyncMock(return_value={"titre": "sans-id"})
    coord = OptieFamilyCoordinator(hass, client, entry)
    coord.async_update_listeners = MagicMock()

    # async_set_album + get_selected_album_photos
    await coord.async_set_album(1, 10)
    assert coord.selected_album[1] == 10
    selected = coord.get_selected_album_photos(1)
    assert selected["album_id"] == 10
    assert selected["total"] >= 1
    # désélection
    await coord.async_set_album(1, None)
    assert coord.get_selected_album_photos(1)["album_id"] is None

    # garde-fou pagination
    coord.album_photos_cache.clear()
    truncated = await coord._ensure_album_photos(1, 77)
    assert len(truncated["photos"]) > 500

    # actualité id invalide + réponse sans id
    assert await coord.async_read_actualite("abc") is None
    assert await coord.async_read_actualite(12) is None
    assert coord.get_selected_actualite_detail() is None
    coord.selected_actualite_id = 12
    coord.actualite_detail_cache[12] = {"id": 12}
    assert coord.get_selected_actualite_detail() == {"id": 12}

    # remember / get_photo_local_url + photo_cache_key fallback
    assert OptieFamilyCoordinator.photo_cache_key("unknown", "x") == "albums:x"
    coord.remember_photo_local_url("9", "/local/optifamily/albums/9.jpg", source="albums")
    assert coord.get_photo_local_url(9, source="albums") == "/local/optifamily/albums/9.jpg"

    # hydrate : exception path, not a dir, skip empty / non-file
    coord2 = OptieFamilyCoordinator(hass, client, entry)
    bad = MagicMock()
    bad.config.path = MagicMock(side_effect=RuntimeError("nope"))
    coord2.hass = bad
    coord2.hydrate_photo_local_urls()

    empty_www = tmp_path / "emptywww"
    empty_www.mkdir()
    hass.config.path = lambda *parts: str(
        (empty_www / parts[0]).joinpath(*parts[1:]) if parts else empty_www
    )
    # www/optifamily n'existe pas → early return
    coord3 = OptieFamilyCoordinator(hass, client, entry)
    coord3.hydrate_photo_local_urls()

    root = tmp_path / "www2" / "www" / "optifamily"
    (root / "albums").mkdir(parents=True)
    # actualites absente → continue (ligne folder not is_dir)
    (root / "albums" / "empty.jpg").write_bytes(b"")
    (root / "albums" / "subdir").mkdir()
    (root / "albums" / "ok.jpg").write_bytes(b"JPEG")
    hass.config.path = lambda *parts: str((tmp_path / "www2").joinpath(*parts))
    coord4 = OptieFamilyCoordinator(hass, client, entry)
    coord4.hydrate_photo_local_urls()
    assert "albums:ok" in coord4.photo_local_urls
    assert "albums:empty" not in coord4.photo_local_urls

    # invalidate : skip bad albums, id non int, photos list
    coord.album_photos_cache[(1, 5)] = {"total": 2, "photos": []}
    coord.selected_album[1] = 5
    coord._invalidate_stale_album_photo_caches(
        {
            1: [
                "skip",
                {"id": None},
                {"id": "not-an-int"},
                {"id": 5, "photos": [{"id": 1}, {"id": 2}]},
            ]
        }
    )
    # total cache 2 == len list 2 → pas invalidé
    assert (1, 5) in coord.album_photos_cache

    # id non-int doit être ignoré (pas de KeyError)
    coord._invalidate_stale_album_photo_caches({1: [{"id": object()}]})

    # reload selected album during update after invalidate
    client.get_me = AsyncMock(return_value={"id": 1})
    client.get_enfants = AsyncMock(return_value=[{"id": 1, "libelle": "A"}])
    client.get_planning_current_month = AsyncMock(return_value={"semaines": []})
    client.get_transmissions = AsyncMock(return_value=[])
    client.get_albums = AsyncMock(return_value=[{"id": 5, "photos": 9, "titre": "A"}])
    client.get_actualites = AsyncMock(return_value={"total": 0, "actualites": []})
    client.get_messages = AsyncMock(return_value=[])
    client.get_creche = AsyncMock(return_value={})
    client.get_documents = AsyncMock(return_value=[])
    client.get_documents_famille = AsyncMock(return_value=[])
    client.get_documents_enfant = AsyncMock(return_value=[])
    client.get_facturation = AsyncMock(return_value=[])
    client.get_tokens = MagicMock(return_value={})
    client.get_album_photos = AsyncMock(return_value={"total": 1, "photos": [{"id": 1}]})
    coord.selected_album[1] = 5
    coord.selected_album[2] = None  # branche aid is None → continue
    coord.album_photos_cache.pop((1, 5), None)
    with (
        patch.object(coord, "_is_in_pause_window", return_value=False),
        patch.object(coord, "_is_creche_closed_pause", return_value=False),
        patch.object(coord, "async_sync_account_metadata", AsyncMock()),
        patch.object(coord, "async_save_tokens", AsyncMock()),
    ):
        await coord._async_update_data()
    assert (1, 5) in coord.album_photos_cache


def test_models_album_medias_and_actualite_edges() -> None:
    from custom_components.optifamily.models import (
        normalize_actualite_detail,
        normalize_actualite_items,
        normalize_downloadable_item,
        normalize_photo_items,
    )

    photo = normalize_downloadable_item(
        {"id": 1, "description": "note", "width": 10, "height": 20}, kind="photo"
    )
    assert photo and photo["description"] == "note"

    album_medias = normalize_downloadable_item(
        {
            "id": 2,
            "images": [{"id": 10}, {"id": 11}, {"id": 12}],
        },
        kind="album",
        limit_photos=2,
    )
    assert album_medias and album_medias["photos_count"] == 3
    assert len(album_medias["photos"]) == 2

    items = normalize_photo_items([{"id": i} for i in range(5)], limit=2)
    assert len(items) == 2

    long_html = "<p>" + ("x" * 250) + "</p>"
    act = normalize_actualite_items({"actualites": [{"id": 1, "contenu": long_html}]})[0]
    assert act["resume"] == ""

    detail = normalize_actualite_detail(
        {
            "id": 1,
            "commentaires": ["bad", {"id": 2, "famille": "F", "contenu": "ok"}],
        }
    )
    assert detail and detail["commentaires_count"] == 1


def test_services_photo_find_and_sniff(hass: MagicMock, tmp_path: Path) -> None:
    data = OptieFamilyData()
    data.albums = {
        1: [
            {"id": 1, "photos": "nope", "medias": "also-nope"},  # nested → []
        ]
    }
    data.actualites = {
        "actualites": [
            "skip",
            {"id": 1, "photos": [{"id": "ap1"}]},
        ]
    }
    coord = MagicMock(spec=OptieFamilyCoordinator)
    coord.data = data
    coord.album_photos_cache = {}
    coord.actualite_detail_cache = {9: {"photos": [{"id": "dp1"}]}}

    assert (
        services_mod._find_download_candidate(coord, kind="photo", item_id="ap1", enfant_id=None)[1]
        == "actualites"
    )
    assert (
        services_mod._find_download_candidate(coord, kind="photo", item_id="dp1", enfant_id=None)[1]
        == "actualites"
    )
    # photos int + medias non-list → nested []
    assert services_mod._find_download_candidate(
        coord, kind="photo", item_id="missing", enfant_id=1
    ) == (None, None)

    assert services_mod._sniff_image_suffix(b"\x89PNG\r\n\x1a\nxxxx") == ".png"
    assert services_mod._sniff_image_suffix(b"GIF89a....") == ".gif"
    assert services_mod._sniff_image_suffix(b"RIFF....WEBP....") == ".webp"
    assert services_mod._sniff_image_suffix(b"nope") == ".bin"


def test_sensors_actualites_and_albums_empty(hass: MagicMock) -> None:
    from custom_components.optifamily.models import Enfant
    import custom_components.optifamily.sensor as sensor_mod

    entry = MagicMock()
    entry.entry_id = "e1"
    entry.data = {CONF_CRECHE_ID: 1, CONF_ENFANTS: []}
    coord = MagicMock(spec=OptieFamilyCoordinator)
    coord.data = None
    coord.selected_actualite_id = None
    coord.actualite_detail_cache = {}
    coord.get_selected_actualite_detail = MagicMock(return_value=None)
    coord.get_selected_album_photos = MagicMock(
        return_value={"album_id": None, "total": 0, "photos": []}
    )
    coord.get_photo_local_url = MagicMock(return_value=None)

    act = sensor_mod.OptieFamilyActualitesSensor(coord, entry)
    assert act.native_value == 0
    attrs = act.extra_state_attributes
    assert attrs["items"] == []
    assert attrs["detail"] is None

    data = OptieFamilyData()
    data.actualites = {
        "total": 1,
        "actualites": [
            {
                "id": 1,
                "titre": "T",
                "photos": [{"id": "p1"}],
            }
        ],
    }
    coord.data = data
    coord.selected_actualite_id = 1
    coord.actualite_detail_cache = {
        1: {"id": 1, "titre": "T", "contenu": "c", "photos": [{"id": "p2"}]}
    }
    coord.get_selected_actualite_detail = MagicMock(return_value=coord.actualite_detail_cache[1])
    coord.get_photo_local_url = MagicMock(
        side_effect=lambda pid, source="albums": f"/local/x/{pid}"
    )
    attrs2 = act.extra_state_attributes
    assert attrs2["detail"]["photos"][0]["cached"] is True

    # _with_local_photo_urls skip non-dict + no id
    out = sensor_mod._with_local_photo_urls(
        coord, ["x", {"id": None}, {"id": "z"}], source="albums"
    )
    assert len(out) == 2
    assert out[0]["cached"] is False

    albums = sensor_mod.OptieFamilyChildAlbumsSensor(coord, entry, Enfant(id=1, libelle="A"), "hub")
    coord.data = None
    assert albums.native_value == 0
