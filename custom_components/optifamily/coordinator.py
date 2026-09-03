"""DataUpdateCoordinator pour l'intégration OptiFamily."""

from __future__ import annotations

from datetime import date, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OptieFamilyApiClient, normalize_enfants
from .const import (
    CONF_CRECHE_ID,
    CONF_CRECHE_NAME,
    CONF_ENFANTS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
    clamp_scan_interval,
)
from .exceptions import (
    OptieFamilyApiError,
    OptieFamilyAuthError,
    OptieFamilyConnectionError,
)

_LOGGER = logging.getLogger(__name__)


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
        self.known_enfant_ids: set[int] = set()
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
            raise UpdateFailed(f"Erreur d'authentification OptiFamily : {err}") from err
        except OptieFamilyConnectionError as err:
            raise UpdateFailed(f"Connexion impossible à l'API OptiFamily : {err}") from err
        except OptieFamilyApiError as err:
            raise UpdateFailed(f"Erreur API OptiFamily : {err}") from err

        await self.async_save_tokens()
        await self.async_sync_account_metadata(result)

        return result
