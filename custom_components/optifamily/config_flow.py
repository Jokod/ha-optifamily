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
    CONF_ENABLED_ENFANTS,
    CONF_ENFANTS,
    CONF_PAUSE_UPDATES,
    CONF_PAUSE_UPDATES_END,
    CONF_PAUSE_UPDATES_START,
    CONF_PAUSE_WHEN_CLOSED,
    DEFAULT_PAUSE_UPDATES,
    DEFAULT_PAUSE_UPDATES_END,
    DEFAULT_PAUSE_UPDATES_START,
    DEFAULT_PAUSE_WHEN_CLOSED,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    clamp_scan_interval,
    scan_interval_from_minutes,
)
from .devices import async_purge_enfant_devices
from .exceptions import (
    OptieFamilyApiError,
    OptieFamilyAuthError,
    OptieFamilyConnectionError,
    OptieFamilySetupError,
)
from .models import iter_enfants

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
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Import depuis configuration.yaml (identifiants via !secret)."""
        return await self.async_step_user(import_data)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Relance l'auth si mot de passe / token invalides."""
        entry_id = self.context.get("entry_id")
        self._reauth_entry = (
            self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        )
        self._flow_data = {
            CONF_USERNAME: entry_data.get(CONF_USERNAME, ""),
            CONF_PASSWORD: "",
            CONF_CRECHE_ID: entry_data.get(CONF_CRECHE_ID),
        }
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirme le nouveau mot de passe."""
        errors: dict[str, str] = {}
        if user_input is not None and self._reauth_entry is not None:
            password = user_input[CONF_PASSWORD]
            username = self._reauth_entry.data[CONF_USERNAME]
            creche_id = self._reauth_entry.data.get(CONF_CRECHE_ID)
            session = async_get_clientsession(self.hass)
            client = OptieFamilyApiClient(
                username=username,
                password=password,
                session=session,
                creche_id=int(creche_id) if creche_id is not None else None,
            )
            try:
                await client.authenticate()
            except OptieFamilyAuthError:
                errors["base"] = "invalid_auth"
            except OptieFamilyConnectionError:
                errors["base"] = "cannot_connect"
            except OptieFamilyApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Erreur inattendue lors de la re-authentification")
                errors["base"] = "unknown"
            if not errors:
                new_data = dict(self._reauth_entry.data)
                new_data[CONF_PASSWORD] = password
                self.hass.config_entries.async_update_entry(self._reauth_entry, data=new_data)
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "username": (
                    self._reauth_entry.data.get(CONF_USERNAME) if self._reauth_entry else ""
                )
            },
        )

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
        # Ne jamais écraser le creche_id choisi par un /me divergent
        me_creche_id = creche.get("id")
        try:
            me_creche_id_int = int(me_creche_id) if me_creche_id is not None else None
        except (TypeError, ValueError):
            me_creche_id_int = None
        if me_creche_id_int is not None and me_creche_id_int != creche_id:
            _LOGGER.warning(
                "creche_id /me (%s) ≠ sélection (%s) — sélection conservée",
                me_creche_id_int,
                creche_id,
            )
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
                CONF_CRECHE_ID: creche_id,
                CONF_CRECHE_NAME: creche_name,
                CONF_ENFANTS: enfants,
            },
            options={
                CONF_ENABLED_ENFANTS: [e["id"] for e in enfants],
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OptieFamilyOptionsFlow()


class OptieFamilyOptionsFlow(OptionsFlow):
    """Flux d'options : polling, pause, enfants suivis."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        enfants = iter_enfants([], self.config_entry.data.get(CONF_ENFANTS, []))
        all_ids = [e.id for e in enfants]
        current_enabled = self.config_entry.options.get(CONF_ENABLED_ENFANTS)
        if current_enabled is None:
            default_enabled = [str(i) for i in all_ids]
        else:
            default_enabled = [str(i) for i in current_enabled]

        if user_input is not None:
            raw_enabled = user_input.get(CONF_ENABLED_ENFANTS, default_enabled)
            if isinstance(raw_enabled, str):
                raw_enabled = [raw_enabled] if raw_enabled else []
            enabled_ids = []
            for value in raw_enabled or []:
                try:
                    enabled_ids.append(int(value))
                except (TypeError, ValueError):
                    continue
            if not enabled_ids and all_ids:
                enabled_ids = list(all_ids)

            excluded = set(all_ids) - set(enabled_ids)
            if excluded:
                async_purge_enfant_devices(self.hass, self.config_entry, excluded)

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
                    CONF_PAUSE_WHEN_CLOSED: bool(
                        user_input.get(CONF_PAUSE_WHEN_CLOSED, DEFAULT_PAUSE_WHEN_CLOSED)
                    ),
                    CONF_ENABLED_ENFANTS: enabled_ids,
                }
            )

        options = self.config_entry.options
        current_seconds = clamp_scan_interval(options.get("scan_interval", DEFAULT_SCAN_INTERVAL))
        enfant_options = [{"value": str(e.id), "label": f"{e.libelle} ({e.id})"} for e in enfants]
        schema_dict: dict[Any, Any] = {
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
            vol.Required(
                CONF_PAUSE_WHEN_CLOSED,
                default=options.get(CONF_PAUSE_WHEN_CLOSED, DEFAULT_PAUSE_WHEN_CLOSED),
            ): BooleanSelector(),
        }
        if enfant_options:
            schema_dict[vol.Required(CONF_ENABLED_ENFANTS, default=default_enabled)] = (
                SelectSelector(
                    SelectSelectorConfig(
                        options=enfant_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            )
        schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "min_minutes": str(MIN_SCAN_INTERVAL // 60),
                "max_minutes": str(MAX_SCAN_INTERVAL // 60),
            },
        )
