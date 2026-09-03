"""Client HTTP asynchrone pour l'API OptiFamily / OptiCrèche."""

from __future__ import annotations

from datetime import date, datetime
import json as json_lib
import logging
from typing import Any

import aiohttp

from .const import (
    API_ACTUALITES,
    API_ALBUMS,
    API_BASE_URL,
    API_DOCUMENTS,
    API_ENFANTS,
    API_FACTURATION,
    API_LOGIN,
    API_LOGOUT,
    API_ME,
    API_MESSAGES,
    API_PLANNING,
    API_PRE_LOGIN,
    API_REFRESH,
    API_TRANSMISSIONS,
    HTTP_TIMEOUT,
)
from .exceptions import (
    OptieFamilyApiError,
    OptieFamilyAuthError,
    OptieFamilyConnectionError,
    OptieFamilySetupError,
)

_LOGGER = logging.getLogger(__name__)


def _normalize_creche(raw: Any) -> dict[str, Any] | None:
    """Normalise une structure crèche depuis la réponse pre-login."""
    if not isinstance(raw, dict):
        return None
    raw_id = raw.get("id", raw.get("crecheId"))
    if raw_id is None:
        return None
    try:
        creche_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    name = raw.get("nom") or raw.get("libelle") or raw.get("label") or f"Crèche {creche_id}"
    return {"id": creche_id, "nom": str(name)}


def _parse_creches_from_response(data: Any) -> list[dict[str, Any]]:
    """Extrait la liste des crèches depuis divers formats de réponse pre-login."""
    if data is None:
        return []

    candidates: list[Any] = []
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        for key in ("creches", "structures", "data"):
            value = data.get(key)
            if isinstance(value, list):
                candidates.extend(value)
        if "creche" in data:
            candidates.append(data["creche"])
        if "crecheId" in data:
            candidates.append({"id": data["crecheId"], "nom": data.get("nom")})

    normalized: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in candidates:
        creche = _normalize_creche(item)
        if creche and creche["id"] not in seen:
            seen.add(creche["id"])
            normalized.append(creche)
    return normalized


def normalize_enfants(enfants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise la liste des enfants pour persistance dans la config entry."""
    result: list[dict[str, Any]] = []
    for enfant in enfants:
        if not isinstance(enfant, dict) or enfant.get("id") is None:
            continue
        try:
            enfant_id = int(enfant["id"])
        except (TypeError, ValueError):
            continue
        result.append(
            {
                "id": enfant_id,
                "libelle": str(enfant.get("libelle") or f"Enfant {enfant_id}"),
            }
        )
    return result


class OptieFamilyApiClient:
    """Client asynchrone pour l'API OptiFamily.

    Gère l'authentification (pre-login / login / refresh), le stockage
    sécurisé des tokens et les appels aux différents endpoints.
    En cas d'expiration, un refresh est tenté puis un login complet.
    """

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        creche_id: int | None = None,
    ) -> None:
        self._username = username
        self._password = password
        self._creche_id = creche_id
        self._session = session
        self._access_token: str | None = None
        self._refresh_token: str | None = None

    @property
    def creche_id(self) -> int | None:
        """Identifiant de la crèche courante."""
        return self._creche_id

    def set_creche_id(self, creche_id: int) -> None:
        """Définit l'identifiant de la crèche."""
        self._creche_id = creche_id

    # ------------------------------------------------------------------
    # Authentification
    # ------------------------------------------------------------------

    async def discover_creches(self) -> list[dict[str, Any]]:
        """Découvre les crèches associées au compte via pre-login."""
        data = await self._request(
            "POST",
            API_PRE_LOGIN,
            json={"username": self._username, "scope": "FAMILLE"},
            authenticated=False,
        )
        creches = _parse_creches_from_response(data)
        if creches:
            return creches
        raise OptieFamilySetupError(
            "Aucune crèche trouvée pour ce compte. Vérifiez votre adresse e-mail."
        )

    async def authenticate(self) -> None:
        """Effectue la séquence pre-login → login et stocke les tokens."""
        if self._creche_id is None:
            creches = await self.discover_creches()
            self._creche_id = creches[0]["id"]

        # Étape 1 : pre-login (initialise la session côté serveur)
        await self._request(
            "POST",
            API_PRE_LOGIN,
            json={"username": self._username, "scope": "FAMILLE"},
            authenticated=False,
        )

        # Étape 2 : login complet
        data = await self._request(
            "POST",
            API_LOGIN,
            json={
                "username": self._username,
                "password": self._password,
                "crecheId": self._creche_id,
                "scope": "FAMILLE",
            },
            authenticated=False,
        )

        self._apply_login_response(data)
        _LOGGER.debug("Authentification OptiFamily réussie")

    async def refresh_tokens(self) -> None:
        """Renouvelle l'access token via POST /auth/refresh.

        Le backend Spring attend un RefreshRequest (corps JSON obligatoire).
        Le champ observé côté login est ``refreshToken``.
        """
        if not self._refresh_token:
            raise OptieFamilyAuthError("Aucun refresh token disponible")

        data = await self._request(
            "POST",
            API_REFRESH,
            json={"refreshToken": self._refresh_token},
            authenticated=False,
            _retry=False,
        )
        self._apply_login_response(data)
        _LOGGER.debug("Refresh token OptiFamily réussi")

    async def ensure_authenticated(self) -> None:
        """Restaure une session : refresh si possible, sinon login complet."""
        if self._access_token:
            return
        if self._refresh_token:
            try:
                await self.refresh_tokens()
                return
            except (OptieFamilyAuthError, OptieFamilyApiError):
                _LOGGER.debug("Refresh impossible, login complet")
        await self.authenticate()

    def _apply_login_response(self, data: Any) -> None:
        """Applique une LoginResponse (login ou refresh)."""
        if not isinstance(data, dict) or "accessToken" not in data:
            raise OptieFamilyAuthError("Réponse d'authentification inattendue")
        self._access_token = data["accessToken"]
        if data.get("refreshToken"):
            self._refresh_token = data["refreshToken"]

    def set_tokens(self, access_token: str, refresh_token: str | None) -> None:
        """Restaure les tokens depuis le stockage persistant."""
        self._access_token = access_token
        self._refresh_token = refresh_token

    def get_tokens(self) -> dict[str, str | None]:
        """Renvoie les tokens courants (pour persistance)."""
        return {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
        }

    @property
    def is_authenticated(self) -> bool:
        """Vrai si un access token est disponible."""
        return self._access_token is not None

    async def logout(self) -> None:
        """Invalide la session côté serveur."""
        try:
            await self._request("GET", API_LOGOUT)
        except Exception:
            pass
        finally:
            self._access_token = None
            self._refresh_token = None

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    async def get_me(self) -> dict[str, Any]:
        """Retourne les informations du compte connecté."""
        return await self._request("GET", API_ME)  # type: ignore[return-value]

    async def get_enfants(self) -> list[dict[str, Any]]:
        """Retourne la liste des enfants du compte."""
        return await self._request("GET", API_ENFANTS)  # type: ignore[return-value]

    async def get_planning(self, enfant_id: int, year: int, month: int) -> dict[str, Any]:
        """Retourne le planning mensuel d'un enfant."""
        path = API_PLANNING.format(enfant_id=enfant_id, year=year, month=month)
        return await self._request("GET", path)  # type: ignore[return-value]

    async def get_planning_current_month(self, enfant_id: int) -> dict[str, Any]:
        """Raccourci : planning du mois courant."""
        now = datetime.now()
        return await self.get_planning(enfant_id, now.year, now.month)

    async def get_transmissions(
        self, enfant_id: int, transmission_date: date | str
    ) -> list[dict[str, Any]]:
        """Retourne les transmissions d'un enfant pour une date (YYYY-MM-DD)."""
        if isinstance(transmission_date, date):
            transmission_date = transmission_date.isoformat()
        path = API_TRANSMISSIONS.format(enfant_id=enfant_id, date=transmission_date)
        return await self._request("GET", path)  # type: ignore[return-value]

    async def get_albums(self, enfant_id: int) -> list[dict[str, Any]]:
        """Retourne les albums d'un enfant."""
        path = API_ALBUMS.format(enfant_id=enfant_id)
        return await self._request("GET", path)  # type: ignore[return-value]

    async def get_actualites(self, from_: int = 0, to: int = 20) -> dict[str, Any]:
        """Retourne les actualités."""
        path = API_ACTUALITES.format(from_=from_, to=to)
        return await self._request("GET", path)  # type: ignore[return-value]

    async def get_messages(self) -> list[dict[str, Any]]:
        """Retourne les messages de la famille."""
        return await self._request("GET", API_MESSAGES)  # type: ignore[return-value]

    async def get_documents(self, creche_id: int | None = None) -> list[dict[str, Any]]:
        """Retourne les documents de la crèche."""
        cid = creche_id or self._creche_id
        if cid is None:
            raise OptieFamilySetupError("Identifiant de crèche non disponible")
        path = API_DOCUMENTS.format(creche_id=cid)
        return await self._request("GET", path)  # type: ignore[return-value]

    async def get_facturation(self) -> list[dict[str, Any]]:
        """Retourne les informations de facturation."""
        return await self._request("GET", API_FACTURATION)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Couche transport
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        authenticated: bool = True,
        _retry: bool = True,
    ) -> Any:
        """Effectue une requête HTTP et gère les erreurs + ré-authentification."""
        url = f"{API_BASE_URL}{path}"
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if authenticated:
            if not self._access_token:
                await self.ensure_authenticated()
            headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            async with self._session.request(
                method,
                url,
                json=json,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
            ) as resp:
                if resp.status == 401 and authenticated and _retry:
                    _LOGGER.debug("Token expiré, refresh puis ré-authentification…")
                    self._access_token = None
                    await self.ensure_authenticated()
                    return await self._request(
                        method, path, json=json, authenticated=True, _retry=False
                    )

                if resp.status == 401:
                    raise OptieFamilyAuthError("Identifiants invalides ou token expiré")

                if resp.status >= 400:
                    text = await resp.text()
                    raise OptieFamilyApiError(resp.status, text[:200])

                # logout / remove-fcm-token : corps vide observé
                if resp.status == 204:
                    return None

                text = await resp.text()
                if not text.strip():
                    return None
                try:
                    return json_lib.loads(text)
                except json_lib.JSONDecodeError as err:
                    raise OptieFamilyApiError(resp.status, "Réponse JSON invalide") from err

        except aiohttp.ServerTimeoutError as err:
            raise OptieFamilyConnectionError(f"Timeout API OptiFamily : {err}") from err
        except aiohttp.ClientConnectionError as err:
            raise OptieFamilyConnectionError(
                f"Impossible de contacter l'API OptiFamily : {err}"
            ) from err
