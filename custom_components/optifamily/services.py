"""Services OptiFamily (journal, documents, téléchargement)."""

from __future__ import annotations

from datetime import date, datetime
import logging
from pathlib import Path
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DOCUMENTS_SCOPES, DOMAIN
from .coordinator import OptieFamilyCoordinator
from .exceptions import OptieFamilyApiError, OptieFamilyError

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_TRANSMISSIONS_DATE = "set_transmissions_date"
SERVICE_SHIFT_TRANSMISSIONS_DATE = "shift_transmissions_date"
SERVICE_SET_DOCUMENTS_SCOPE = "set_documents_scope"
SERVICE_DOWNLOAD = "download"

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")

_SET_SCHEMA = vol.Schema(
    {
        vol.Required("date"): cv.date,
        vol.Optional("config_entry_id"): cv.string,
    }
)
_SHIFT_SCHEMA = vol.Schema(
    {
        vol.Required("days", default=-1): vol.All(vol.Coerce(int), vol.Range(min=-30, max=30)),
        vol.Optional("config_entry_id"): cv.string,
    }
)
_DOCS_SCOPE_SCHEMA = vol.Schema(
    {
        vol.Required("scope"): vol.In(DOCUMENTS_SCOPES),
        vol.Optional("enfant_id"): vol.Coerce(int),
        vol.Optional("config_entry_id"): cv.string,
    }
)
_DOWNLOAD_SCHEMA = vol.Schema(
    {
        vol.Required("kind"): vol.In(["photo", "document", "facture"]),
        vol.Required("id"): cv.string,
        vol.Optional("config_entry_id"): cv.string,
        vol.Optional("enfant_id"): vol.Coerce(int),
        vol.Optional("download_url"): cv.string,
    }
)


def _parse_day(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _coordinators(
    hass: HomeAssistant, entry_id: str | None = None
) -> list[tuple[ConfigEntry, OptieFamilyCoordinator]]:
    out: list[tuple[ConfigEntry, OptieFamilyCoordinator]] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry_id and entry.entry_id != entry_id:
            continue
        coordinator = getattr(entry, "runtime_data", None)
        if isinstance(coordinator, OptieFamilyCoordinator):
            out.append((entry, coordinator))
    return out


async def _async_set_date(call: ServiceCall) -> None:
    day = _parse_day(call.data["date"])
    entry_id = call.data.get("config_entry_id")
    targets = _coordinators(call.hass, entry_id)
    if not targets:
        _LOGGER.warning("Aucun coordinator OptiFamily pour set_transmissions_date")
        return
    for _entry, coordinator in targets:
        await coordinator.async_set_transmissions_view_date(day)


async def _async_shift_date(call: ServiceCall) -> None:
    days = int(call.data["days"])
    entry_id = call.data.get("config_entry_id")
    targets = _coordinators(call.hass, entry_id)
    if not targets:
        _LOGGER.warning("Aucun coordinator OptiFamily pour shift_transmissions_date")
        return
    for _entry, coordinator in targets:
        await coordinator.async_shift_transmissions_view_date(days)


async def _async_set_documents_scope(call: ServiceCall) -> None:
    entry_id = call.data.get("config_entry_id")
    targets = _coordinators(call.hass, entry_id)
    if not targets:
        _LOGGER.warning("Aucun coordinator OptiFamily pour set_documents_scope")
        return
    scope = call.data["scope"]
    enfant_id = call.data.get("enfant_id")
    for _entry, coordinator in targets:
        await coordinator.async_set_documents_scope(scope, enfant_id)


def _find_download_candidate(
    coordinator: OptieFamilyCoordinator,
    *,
    kind: str,
    item_id: str,
    enfant_id: int | None,
) -> dict[str, Any] | None:
    data = coordinator.data
    if not data:
        return None
    pools: list[Any] = []
    if kind == "document":
        pools.extend(data.documents or [])
        pools.extend(getattr(data, "documents_famille", None) or [])
        for vals in (getattr(data, "documents_enfant", None) or {}).values():
            pools.extend(vals or [])
    elif kind == "facture":
        pools.extend(data.facturation or [])
    elif kind == "photo":
        albums_map = data.albums or {}
        if enfant_id is not None:
            albums = albums_map.get(enfant_id, [])
        else:
            albums = [a for vals in albums_map.values() for a in vals]
        for album in albums:
            if not isinstance(album, dict):
                continue
            if str(album.get("id")) == item_id:
                return album
            for photo in album.get("photos") or album.get("medias") or album.get("images") or []:
                if isinstance(photo, dict) and str(photo.get("id")) == item_id:
                    return photo
        return None
    for raw in pools:
        if isinstance(raw, dict) and str(raw.get("id")) == item_id:
            return raw
    return None


async def _async_download(call: ServiceCall) -> None:
    kind = call.data["kind"]
    item_id = str(call.data["id"])
    entry_id = call.data.get("config_entry_id")
    enfant_id = call.data.get("enfant_id")
    explicit_url = call.data.get("download_url")
    targets = _coordinators(call.hass, entry_id)
    if not targets:
        _LOGGER.warning("Aucun coordinator OptiFamily pour download")
        return
    entry, coordinator = targets[0]
    candidate = _find_download_candidate(
        coordinator, kind=kind, item_id=item_id, enfant_id=enfant_id
    )
    url = explicit_url
    if not url and isinstance(candidate, dict):
        for key in (
            "download_url",
            "downloadUrl",
            "url",
            "mediaUrl",
            "media_url",
            "fichierUrl",
            "fileUrl",
            "path",
        ):
            raw = candidate.get(key)
            if raw:
                url = str(raw)
                break
    if not url:
        _LOGGER.warning(
            "Téléchargement impossible (kind=%s id=%s) : pas d'URL/media — downloadable=false",
            kind,
            item_id,
        )
        call.hass.bus.async_fire(
            f"{DOMAIN}_download_failed",
            {"kind": kind, "id": item_id, "reason": "not_downloadable"},
        )
        return

    try:
        payload = await coordinator.client.download_bytes(url)
    except (OptieFamilyApiError, OptieFamilyError) as err:
        _LOGGER.warning("Échec téléchargement OptiFamily : %s", err)
        call.hass.bus.async_fire(
            f"{DOMAIN}_download_failed",
            {"kind": kind, "id": item_id, "reason": str(err)},
        )
        return

    safe_kind = _SAFE_NAME.sub("_", kind)
    safe_id = _SAFE_NAME.sub("_", item_id)[:80]
    www = Path(call.hass.config.path("www")) / "optifamily"
    www.mkdir(parents=True, exist_ok=True)
    filename = f"{safe_kind}_{safe_id}.bin"
    # Extension depuis URL si possible
    suffix = Path(str(url).split("?", 1)[0]).suffix
    if suffix and len(suffix) <= 5:
        filename = f"{safe_kind}_{safe_id}{suffix}"
    target = www / filename
    target.write_bytes(payload)
    local_url = f"/local/optifamily/{filename}"
    _LOGGER.info("Fichier OptiFamily téléchargé : %s", local_url)
    call.hass.bus.async_fire(
        f"{DOMAIN}_download_ready",
        {
            "kind": kind,
            "id": item_id,
            "path": str(target),
            "url": local_url,
            "config_entry_id": entry.entry_id,
        },
    )


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Enregistre les services une seule fois."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_TRANSMISSIONS_DATE):
        return
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TRANSMISSIONS_DATE,
        _async_set_date,
        schema=_SET_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SHIFT_TRANSMISSIONS_DATE,
        _async_shift_date,
        schema=_SHIFT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DOCUMENTS_SCOPE,
        _async_set_documents_scope,
        schema=_DOCS_SCOPE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DOWNLOAD,
        _async_download,
        schema=_DOWNLOAD_SCHEMA,
    )


@callback
def async_unload_services(hass: HomeAssistant) -> None:
    """Retire les services s'il ne reste aucune entrée."""
    if hass.config_entries.async_entries(DOMAIN):
        return
    for name in (
        SERVICE_SET_TRANSMISSIONS_DATE,
        SERVICE_SHIFT_TRANSMISSIONS_DATE,
        SERVICE_SET_DOCUMENTS_SCOPE,
        SERVICE_DOWNLOAD,
    ):
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)
