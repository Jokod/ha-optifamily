"""DataUpdateCoordinator pour l'intégration OptiFamily."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
import logging
from time import monotonic
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OptieFamilyApiClient, normalize_enfants
from .const import (
    CONF_CRECHE_ID,
    CONF_CRECHE_NAME,
    CONF_ENFANTS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLANNING_CACHE_TTL,
    PLANNING_ERROR_RETRY,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
    clamp_scan_interval,
)
from .exceptions import (
    OptieFamilyApiError,
    OptieFamilyAuthError,
    OptieFamilyConnectionError,
    OptieFamilyError,
)

_LOGGER = logging.getLogger(__name__)


class _PlanningCacheEntry:
    """Planning mensuel mis en cache pour éviter de rejouer l'API à chaque navigation."""

    __slots__ = ("data", "fetched_at", "ok")

    def __init__(self, data: dict[str, Any], *, ok: bool) -> None:
        self.data = data
        self.ok = ok
        self.fetched_at = monotonic()

    def is_fresh(self) -> bool:
        ttl = PLANNING_CACHE_TTL if self.ok else PLANNING_ERROR_RETRY
        return (monotonic() - self.fetched_at) < ttl


class OptieFamilyData:
    """Conteneur typé des données fraîches renvoyées par le coordinator."""

    __slots__ = (
        "actualites",
        "albums",
        "documents",
        "enfants",
        "facturation",
        "me",
        "messages",
        "persisted_enfants",
        "plannings",
        "transmissions",
    )

    def __init__(self) -> None:
        self.me: dict[str, Any] = {}
        self.enfants: list[dict[str, Any]] = []
        self.plannings: dict[int, dict[str, Any]] = {}
        self.transmissions: dict[int, list[dict[str, Any]]] = {}
        self.albums: dict[int, list[dict[str, Any]]] = {}
        self.actualites: dict[str, Any] = {}
        self.messages: list[dict[str, Any]] = []
        self.documents: list[dict[str, Any]] = []
        self.facturation: list[dict[str, Any]] = []
        self.persisted_enfants: list[dict[str, Any]] = []


class OptieFamilyCoordinator(DataUpdateCoordinator[OptieFamilyData]):
    """Coordinator central — récupère toutes les données à intervalle régulier."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: OptieFamilyApiClient,
        entry: ConfigEntry,
    ) -> None:
        scan_interval = clamp_scan_interval(
            entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.entry = entry
        self.scan_interval = scan_interval
        self.last_sync_at: datetime | None = None
        self.known_enfant_ids: set[int] = set()
        self.known_calendar_enfant_ids: set[int] = set()
        self._planning_cache: dict[tuple[int, int, int], _PlanningCacheEntry] = {}
        self._planning_inflight: dict[tuple[int, int, int], asyncio.Task[dict[str, Any]]] = {}
        _LOGGER.debug("Intervalle de rafraîchissement OptiFamily : %ss", scan_interval)
        self._store: Store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}.{entry.entry_id}",
        )

    # ------------------------------------------------------------------
    # Persistance des tokens
    # ------------------------------------------------------------------

    async def async_save_tokens(self) -> None:
        """Sauvegarde les tokens dans le store chiffré de HA."""
        tokens = self.client.get_tokens()
        await self._store.async_save(tokens)
        _LOGGER.debug("Tokens OptiFamily sauvegardés")

    async def async_load_tokens(self) -> bool:
        """Charge les tokens persistés. Renvoie True si des tokens existent."""
        data = await self._store.async_load()
        if data and data.get("access_token"):
            self.client.set_tokens(data["access_token"], data.get("refresh_token"))
            return True
        return False

    async def async_clear_tokens(self) -> None:
        """Supprime les tokens persistés (déconnexion / suppression config)."""
        await self._store.async_remove()

    # ------------------------------------------------------------------
    # Synchronisation config entry (creche_id, enfants)
    # ------------------------------------------------------------------

    @callback
    def _enfants_changed(
        self,
        current: list[dict[str, Any]],
        previous: list[dict[str, Any]],
    ) -> bool:
        current_ids = {e["id"] for e in current}
        previous_ids = {e["id"] for e in previous}
        return current_ids != previous_ids

    async def async_sync_account_metadata(self, data: OptieFamilyData) -> None:
        """Persiste creche_id et enfants dans la config entry si nécessaire."""
        new_data = dict(self.entry.data)
        changed = False
        reload_required = False

        creche = data.me.get("creche") if isinstance(data.me, dict) else None
        if isinstance(creche, dict) and creche.get("id") is not None:
            try:
                creche_id = int(creche["id"])
            except (TypeError, ValueError):
                creche_id = None
            if creche_id is not None:
                if new_data.get(CONF_CRECHE_ID) != creche_id:
                    new_data[CONF_CRECHE_ID] = creche_id
                    changed = True
                if self.client.creche_id != creche_id:
                    self.client.set_creche_id(creche_id)
                creche_name = str(creche.get("nom") or "")
                if creche_name and new_data.get(CONF_CRECHE_NAME) != creche_name:
                    new_data[CONF_CRECHE_NAME] = creche_name
                    changed = True

        enfants = normalize_enfants(data.enfants)
        previous_enfants = new_data.get(CONF_ENFANTS, [])
        if enfants != previous_enfants:
            new_data[CONF_ENFANTS] = enfants
            changed = True
            reload_required = self._enfants_changed(enfants, previous_enfants)

        if not changed:
            return

        self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        _LOGGER.debug(
            "Métadonnées OptiFamily synchronisées (creche_id=%s, %d enfant(s))",
            new_data.get(CONF_CRECHE_ID),
            len(enfants),
        )

        if reload_required:
            new_ids = {e["id"] for e in enfants}
            added_ids = new_ids - self.known_enfant_ids
            if added_ids:
                _LOGGER.info(
                    "Nouveau(x) enfant(s) détecté(s) : %s",
                    ", ".join(str(i) for i in sorted(added_ids)),
                )

    # ------------------------------------------------------------------
    # Mise à jour
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> OptieFamilyData:
        """Méthode appelée automatiquement par HA toutes les N secondes."""
        result = OptieFamilyData()
        result.persisted_enfants = list(self.entry.data.get(CONF_ENFANTS, []))
        today = date.today()

        try:
            result.me = await self.client.get_me()
            result.enfants = await self.client.get_enfants()

            for enfant in result.enfants:
                eid = enfant["id"]
                try:
                    result.plannings[eid] = await self.client.get_planning_current_month(eid)
                except Exception as err:
                    _LOGGER.warning(
                        "Impossible de récupérer le planning de l'enfant %s : %s",
                        eid,
                        err,
                    )

                try:
                    result.transmissions[eid] = await self.client.get_transmissions(eid, today)
                except Exception as err:
                    _LOGGER.warning(
                        "Impossible de récupérer les transmissions de l'enfant %s : %s",
                        eid,
                        err,
                    )

                try:
                    result.albums[eid] = await self.client.get_albums(eid)
                except Exception as err:
                    _LOGGER.warning(
                        "Impossible de récupérer les albums de l'enfant %s : %s",
                        eid,
                        err,
                    )

            result.actualites = await self.client.get_actualites(0, 20)
            result.messages = await self.client.get_messages()
            result.documents = await self.client.get_documents()
            result.facturation = await self.client.get_facturation()

        except OptieFamilyAuthError as err:
            raise ConfigEntryAuthFailed(f"Erreur d'authentification OptiFamily : {err}") from err
        except OptieFamilyConnectionError as err:
            raise UpdateFailed(f"Connexion impossible à l'API OptiFamily : {err}") from err
        except OptieFamilyApiError as err:
            raise UpdateFailed(f"Erreur API OptiFamily : {err}") from err
        except OptieFamilyError as err:
            raise UpdateFailed(f"Erreur OptiFamily : {err}") from err

        await self.async_save_tokens()
        await self.async_sync_account_metadata(result)

        for eid, planning in result.plannings.items():
            self._planning_cache[(eid, today.year, today.month)] = _PlanningCacheEntry(
                planning, ok=True
            )

        self.last_sync_at = datetime.now(UTC)
        return result

    async def async_get_planning_month(
        self, enfant_id: int, year: int, month: int
    ) -> dict[str, Any]:
        """Planning d'un mois : mois courant via le polling, autres mois en cache.

        Un même mois n'est demandé qu'une fois à l'API (navigation calendrier,
        plusieurs cartes, clics répétés). TTL 30 min, 5 min après un échec.
        """
        key = (enfant_id, year, month)
        today = date.today()
        if (
            year == today.year
            and month == today.month
            and self.data
            and enfant_id in self.data.plannings
        ):
            planning = self.data.plannings[enfant_id]
            self._planning_cache[key] = _PlanningCacheEntry(planning, ok=True)
            return planning

        cached = self._planning_cache.get(key)
        if cached is not None and cached.is_fresh():
            return cached.data

        task = self._planning_inflight.get(key)
        if task is None or task.done():
            task = asyncio.create_task(self._fetch_planning_month(enfant_id, year, month))
            self._planning_inflight[key] = task
        try:
            return await task
        finally:
            current = self._planning_inflight.get(key)
            if current is task and task.done():
                del self._planning_inflight[key]

    async def _fetch_planning_month(self, enfant_id: int, year: int, month: int) -> dict[str, Any]:
        key = (enfant_id, year, month)
        try:
            planning = await self.client.get_planning(enfant_id, year, month)
        except Exception as err:
            _LOGGER.warning(
                "Impossible de récupérer le planning %s-%02d de l'enfant %s : %s",
                year,
                month,
                enfant_id,
                err,
            )
            self._planning_cache[key] = _PlanningCacheEntry({}, ok=False)
            return {}
        if not isinstance(planning, dict):
            self._planning_cache[key] = _PlanningCacheEntry({}, ok=False)
            return {}
        self._planning_cache[key] = _PlanningCacheEntry(planning, ok=True)
        return planning
