"""Services OptiFamily (journal, documents, albums, actualités, téléchargement)."""

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

from .api import OptieFamilyApiClient
from .const import (
    DOCUMENTS_SCOPES,
    DOMAIN,
    PHOTO_DIR_ACTUALITES,
    PHOTO_DIR_ALBUMS,
    PHOTO_SOURCES,
)
from .coordinator import OptieFamilyCoordinator
from .exceptions import OptieFamilyApiError, OptieFamilyError

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_TRANSMISSIONS_DATE = "set_transmissions_date"
SERVICE_SHIFT_TRANSMISSIONS_DATE = "shift_transmissions_date"
SERVICE_SET_DOCUMENTS_SCOPE = "set_documents_scope"
SERVICE_SET_ALBUM = "set_album"
SERVICE_READ_ACTUALITE = "read_actualite"
SERVICE_DOWNLOAD = "download"
SERVICE_REFRESH = "refresh"

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")

_SET_SCHEMA = vol.Schema(
    {
        vol.Optional("date"): cv.date,
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
_SET_ALBUM_SCHEMA = vol.Schema(
    {
        vol.Required("enfant_id"): vol.Coerce(int),
        vol.Optional("album_id"): vol.Any(None, vol.Coerce(int)),
        vol.Optional("config_entry_id"): cv.string,
    }
)
_READ_ACTUALITE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): vol.Any(cv.string, vol.Coerce(int)),
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
        vol.Optional("source"): vol.In(PHOTO_SOURCES),
    }
)
_REFRESH_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
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
    raw = call.data.get("date")
    day = _parse_day(raw) if raw is not None else date.today()
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


async def _async_set_album(call: ServiceCall) -> None:
    entry_id = call.data.get("config_entry_id")
    targets = _coordinators(call.hass, entry_id)
    if not targets:
        _LOGGER.warning("Aucun coordinator OptiFamily pour set_album")
        return
    enfant_id = int(call.data["enfant_id"])
    album_id = call.data.get("album_id")
    for _entry, coordinator in targets:
        await coordinator.async_set_album(enfant_id, album_id)


async def _async_read_actualite(call: ServiceCall) -> None:
    entry_id = call.data.get("config_entry_id")
    targets = _coordinators(call.hass, entry_id)
    if not targets:
        _LOGGER.warning("Aucun coordinator OptiFamily pour read_actualite")
        return
    actualite_id = call.data["id"]
    for _entry, coordinator in targets:
        await coordinator.async_read_actualite(actualite_id)


def _find_download_candidate(
    coordinator: OptieFamilyCoordinator,
    *,
    kind: str,
    item_id: str,
    enfant_id: int | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Retourne (item, source_photo) — source_photo = albums|actualites pour kind=photo."""
    data = coordinator.data
    if not data:
        return None, None
    pools: list[Any] = []
    if kind == "document":
        pools.extend(data.documents or [])
        pools.extend(data.documents_famille or [])
        for vals in (data.documents_enfant or {}).values():
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
            cover = album.get("photo")
            if isinstance(cover, dict) and str(cover.get("id")) == item_id:
                return cover, PHOTO_DIR_ALBUMS
            nested = album.get("photos")
            if not isinstance(nested, list):
                nested = album.get("medias") or album.get("images") or []
            if not isinstance(nested, list):
                nested = []
            for photo in nested:
                if isinstance(photo, dict) and str(photo.get("id")) == item_id:
                    return photo, PHOTO_DIR_ALBUMS
        for (eid, _aid), cached in (coordinator.album_photos_cache or {}).items():
            if enfant_id is not None and eid != enfant_id:
                continue
            for photo in cached.get("photos") or []:
                if isinstance(photo, dict) and str(photo.get("id")) == item_id:
                    return photo, PHOTO_DIR_ALBUMS
        for act in (data.actualites or {}).get("actualites") or []:
            if not isinstance(act, dict):
                continue
            for photo in act.get("photos") or []:
                if isinstance(photo, dict) and str(photo.get("id")) == item_id:
                    return photo, PHOTO_DIR_ACTUALITES
        for detail in (coordinator.actualite_detail_cache or {}).values():
            for photo in detail.get("photos") or []:
                if isinstance(photo, dict) and str(photo.get("id")) == item_id:
                    return photo, PHOTO_DIR_ACTUALITES
        return None, None
    for raw in pools:
        if isinstance(raw, dict) and str(raw.get("id")) == item_id:
            return raw, None
    return None, None


def _sniff_image_suffix(payload: bytes) -> str:
    """Déduit l'extension depuis les magic bytes."""
    if payload.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if payload.startswith(b"GIF87a") or payload.startswith(b"GIF89a"):
        return ".gif"
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return ".webp"
    return ".bin"


def _photo_subdir(source: str | None) -> str:
    if source in PHOTO_SOURCES:
        return source
    return PHOTO_DIR_ALBUMS


def _existing_photo_local(www: Path, photo_id: str, *, source: str) -> tuple[Path, str] | None:
    """Retourne (path, local_url) si la photo est déjà sur disque."""
    folder = www / source
    safe_id = _SAFE_NAME.sub("_", photo_id)[:80]
    for suffix in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bin"):
        candidate = folder / f"{safe_id}{suffix}"
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate, f"/local/optifamily/{source}/{candidate.name}"
    return None


async def _async_download(call: ServiceCall) -> None:
    kind = call.data["kind"]
    item_id = str(call.data["id"])
    entry_id = call.data.get("config_entry_id")
    enfant_id = call.data.get("enfant_id")
    explicit_url = call.data.get("download_url")
    explicit_source = call.data.get("source")
    targets = _coordinators(call.hass, entry_id)
    if not targets:
        _LOGGER.warning("Aucun coordinator OptiFamily pour download")
        return
    entry, coordinator = targets[0]

    www = Path(call.hass.config.path("www")) / "optifamily"
    www.mkdir(parents=True, exist_ok=True)

    candidate, detected_source = _find_download_candidate(
        coordinator, kind=kind, item_id=item_id, enfant_id=enfant_id
    )
    photo_source = _photo_subdir(explicit_source or detected_source)

    # Photos : réutiliser le fichier local si déjà téléchargé (pas de re-appel API)
    if kind == "photo":
        existing = _existing_photo_local(www, item_id, source=photo_source)
        if existing:
            _path, local_url = existing
            coordinator.remember_photo_local_url(item_id, local_url, source=photo_source)
            _LOGGER.debug("Photo OptiFamily déjà en cache local : %s", local_url)
            call.hass.bus.async_fire(
                f"{DOMAIN}_download_ready",
                {
                    "kind": kind,
                    "id": item_id,
                    "source": photo_source,
                    "path": str(_path),
                    "url": local_url,
                    "cached": True,
                    "config_entry_id": entry.entry_id,
                },
            )
            return

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
    if not url and kind == "photo":
        url = OptieFamilyApiClient.photo_path(item_id)
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
    if kind == "photo":
        folder = www / photo_source
        folder.mkdir(parents=True, exist_ok=True)
        filename = f"{safe_id}{_sniff_image_suffix(payload)}"
        target = folder / filename
        local_url = f"/local/optifamily/{photo_source}/{filename}"
        target.write_bytes(payload)
        coordinator.remember_photo_local_url(item_id, local_url, source=photo_source)
    else:
        filename = f"{safe_kind}_{safe_id}.bin"
        url_path = str(url).split("?", 1)[0]
        suffix = Path(url_path).suffix.lower()
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
            "source": photo_source if kind == "photo" else None,
            "path": str(target),
            "url": local_url,
            "cached": False,
            "config_entry_id": entry.entry_id,
        },
    )


async def _async_refresh(call: ServiceCall) -> None:
    """Demande une synchronisation API immédiate."""
    entry_id = call.data.get("config_entry_id")
    targets = _coordinators(call.hass, entry_id)
    if not targets:
        _LOGGER.warning("Aucun coordinator OptiFamily pour refresh")
        return
    for _entry, coordinator in targets:
        await coordinator.async_request_sync()


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
        SERVICE_SET_ALBUM,
        _async_set_album,
        schema=_SET_ALBUM_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_READ_ACTUALITE,
        _async_read_actualite,
        schema=_READ_ACTUALITE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DOWNLOAD,
        _async_download,
        schema=_DOWNLOAD_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        _async_refresh,
        schema=_REFRESH_SCHEMA,
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
        SERVICE_SET_ALBUM,
        SERVICE_READ_ACTUALITE,
        SERVICE_DOWNLOAD,
        SERVICE_REFRESH,
    ):
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)
