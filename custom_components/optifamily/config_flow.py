"""Config Flow pour l'intégration OptiFamily."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)
import voluptuous as vol

from .api import OptieFamilyApiClient, normalize_enfants
from .const import (
    CONF_CRECHE_ID,
    CONF_CRECHE_NAME,
    CONF_ENFANTS,
    CONF_PAUSE_UPDATES,
    CONF_PAUSE_UPDATES_END,
    CONF_PAUSE_UPDATES_START,
    DEFAULT_PAUSE_UPDATES,
    DEFAULT_PAUSE_UPDATES_END,
    DEFAULT_PAUSE_UPDATES_START,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    clamp_scan_interval,
    scan_interval_from_minutes,
)
from .exceptions import (
    OptieFamilyApiError,
    OptieFamilyAuthError,
    OptieFamilyConnectionError,
    OptieFamilySetupError,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="email")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


class OptieFamilyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Flux de configuration guidé pour OptiFamily."""

    VERSION = 2

    def __init__(self) -> None:
        self._flow_data: dict[str, Any] = {}
        self._creches: list[dict[str, Any]] = []

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import depuis configuration.yaml (identifiants via !secret)."""
        return await self.async_step_user(import_data)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Étape principale : saisie des identifiants uniquement."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]

            self._flow_data = {
                CONF_USERNAME: username,
                CONF_PASSWORD: password,
            }

            session = async_get_clientsession(self.hass)
            client = OptieFamilyApiClient(
                username=username,
                password=password,
                session=session,
            )

            try:
                self._creches = await client.discover_creches()
            except OptieFamilyAuthError:
                errors["base"] = "invalid_auth"
            except OptieFamilyConnectionError:
                errors["base"] = "cannot_connect"
            except OptieFamilySetupError:
                errors["base"] = "no_creche"
            except OptieFamilyApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Erreur inattendue lors de la découverte du compte")
                errors["base"] = "unknown"

            if not errors:
                if len(self._creches) == 1:
                    creche_id = int(self._creches[0]["id"])
                    await self.async_set_unique_id(f"{username.lower()}_{creche_id}")
                    self._abort_if_unique_id_configured()
                    return await self._async_create_entry_from_client(client, creche_id)
                return await self.async_step_creche()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={
                "import_hint": (
                    "Vous pouvez aussi importer vos identifiants via "
                    "`configuration.yaml` et `secrets.yaml`."
                )
            },
        )

    async def async_step_creche(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Sélection de la crèche si plusieurs structures sont disponibles."""
        errors: dict[str, str] = {}

        if user_input is not None:
            creche_id = int(user_input[CONF_CRECHE_ID])
            await self.async_set_unique_id(f"{self._flow_data[CONF_USERNAME].lower()}_{creche_id}")
            self._abort_if_unique_id_configured()
            session = async_get_clientsession(self.hass)
            client = OptieFamilyApiClient(
                username=self._flow_data[CONF_USERNAME],
                password=self._flow_data[CONF_PASSWORD],
                session=session,
                creche_id=creche_id,
            )
            try:
                return await self._async_create_entry_from_client(client, creche_id)
            except OptieFamilyAuthError:
                errors["base"] = "invalid_auth"
            except OptieFamilyConnectionError:
                errors["base"] = "cannot_connect"
            except OptieFamilyApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Erreur inattendue lors de l'authentification")
                errors["base"] = "unknown"

        options = [
            {"value": str(c["id"]), "label": f"{c['nom']} ({c['id']})"} for c in self._creches
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_CRECHE_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

        return self.async_show_form(
            step_id="creche",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "count": str(len(self._creches)),
            },
        )

    async def _async_create_entry_from_client(
        self,
        client: OptieFamilyApiClient,
        creche_id: int,
    ) -> ConfigFlowResult:
        """Authentifie, découvre les métadonnées et crée l'entrée de config."""
        client.set_creche_id(creche_id)
        await client.authenticate()

        me = await client.get_me()
        enfants = normalize_enfants(await client.get_enfants())

        creche = me.get("creche", {}) if isinstance(me, dict) else {}
        creche_name = str(creche.get("nom") or "")
        account_name = str(me.get("nom") or self._flow_data[CONF_USERNAME])

        title = f"OptiFamily - {account_name}"
        if creche_name:
            title = f"OptiFamily - {creche_name}"

        return self.async_create_entry(
            title=title,
            data={
                CONF_USERNAME: self._flow_data[CONF_USERNAME],
                CONF_PASSWORD: self._flow_data[CONF_PASSWORD],
                CONF_CRECHE_ID: int(creche.get("id") or creche_id),
                CONF_CRECHE_NAME: creche_name,
                CONF_ENFANTS: enfants,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OptieFamilyOptionsFlow()


class OptieFamilyOptionsFlow(OptionsFlow):
    """Flux d'options : intervalle de polling + pause nocturne."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    "scan_interval": scan_interval_from_minutes(
                        user_input["scan_interval_minutes"]
                    ),
                    CONF_PAUSE_UPDATES: bool(user_input.get(CONF_PAUSE_UPDATES, True)),
                    CONF_PAUSE_UPDATES_START: str(
                        user_input.get(CONF_PAUSE_UPDATES_START, DEFAULT_PAUSE_UPDATES_START)
                    ),
                    CONF_PAUSE_UPDATES_END: str(
                        user_input.get(CONF_PAUSE_UPDATES_END, DEFAULT_PAUSE_UPDATES_END)
                    ),
                }
            )

        options = self.config_entry.options
        current_seconds = clamp_scan_interval(options.get("scan_interval", DEFAULT_SCAN_INTERVAL))
        schema = vol.Schema(
            {
                vol.Required(
                    "scan_interval_minutes",
                    default=current_seconds // 60,
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL // 60,
                        max=MAX_SCAN_INTERVAL // 60,
                        step=1,
                        mode=NumberSelectorMode.SLIDER,
                        unit_of_measurement="min",
                    )
                ),
                vol.Required(
                    CONF_PAUSE_UPDATES,
                    default=options.get(CONF_PAUSE_UPDATES, DEFAULT_PAUSE_UPDATES),
                ): BooleanSelector(),
                vol.Required(
                    CONF_PAUSE_UPDATES_START,
                    default=options.get(CONF_PAUSE_UPDATES_START, DEFAULT_PAUSE_UPDATES_START),
                ): TimeSelector(),
                vol.Required(
                    CONF_PAUSE_UPDATES_END,
                    default=options.get(CONF_PAUSE_UPDATES_END, DEFAULT_PAUSE_UPDATES_END),
                ): TimeSelector(),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "min_minutes": str(MIN_SCAN_INTERVAL // 60),
                "max_minutes": str(MAX_SCAN_INTERVAL // 60),
            },
        )
