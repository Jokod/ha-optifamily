"""Intégration Home Assistant — OptiFamily / OptiCrèche."""

from __future__ import annotations

import contextlib
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OptieFamilyApiClient
from .blueprints import async_install_blueprints, async_uninstall_blueprints
from .config import CONFIG_SCHEMA
from .config import async_setup as async_setup_config
from .const import CONF_CRECHE_ID, CONF_PASSWORD, CONF_USERNAME, DOMAIN, PLATFORMS
from .coordinator import OptieFamilyCoordinator
from .exceptions import (
    OptieFamilyApiError,
    OptieFamilyAuthError,
    OptieFamilyConnectionError,
    OptieFamilySetupError,
)
from .services import async_setup_services, async_unload_services
from .themes import async_install_theme, async_uninstall_theme

_LOGGER = logging.getLogger(__name__)

__all__ = ["CONFIG_SCHEMA", "async_setup", "async_setup_entry"]

type OptieFamilyConfigEntry = ConfigEntry[OptieFamilyCoordinator]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Permet l'import via configuration.yaml (identifiants dans secrets.yaml)."""
    return await async_setup_config(hass, config)


async def async_setup_entry(hass: HomeAssistant, entry: OptieFamilyConfigEntry) -> bool:
    """Configure l'entrée de config OptiFamily."""
    session = async_get_clientsession(hass)

    creche_id = entry.data.get(CONF_CRECHE_ID)
    client = OptieFamilyApiClient(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        session=session,
        creche_id=int(creche_id) if creche_id is not None else None,
    )

    coordinator = OptieFamilyCoordinator(hass, client, entry)

    has_tokens = await coordinator.async_load_tokens()

    if not has_tokens or client.creche_id is None:
        try:
            if client.creche_id is None:
                creches = await client.discover_creches()
                client.set_creche_id(creches[0]["id"])
            await client.ensure_authenticated()
            await coordinator.async_save_tokens()
        except OptieFamilyAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except OptieFamilyConnectionError as err:
            raise ConfigEntryNotReady(str(err)) from err
        except OptieFamilySetupError as err:
            raise ConfigEntryNotReady(str(err)) from err
        except OptieFamilyApiError as err:
            raise ConfigEntryNotReady(str(err)) from err

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        _LOGGER.warning("Token persisté invalide, refresh puis ré-authentification…")
        try:
            await client.ensure_authenticated()
            await coordinator.async_save_tokens()
            await coordinator.async_config_entry_first_refresh()
        except OptieFamilyAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except OptieFamilyConnectionError as err:
            raise ConfigEntryNotReady(str(err)) from err
        except OptieFamilyApiError as err:
            raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = coordinator

    async_setup_services(hass)
    await async_install_blueprints(hass)
    await async_install_theme(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: OptieFamilyConfigEntry) -> bool:
    """Supprime l'entrée de config."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        with contextlib.suppress(Exception):
            await entry.runtime_data.client.logout()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: OptieFamilyConfigEntry) -> None:
    """Nettoyage à la suppression : tokens, puis blueprints s'il ne reste aucune entrée."""
    if entry.runtime_data:
        await entry.runtime_data.async_clear_tokens()
    remaining = [
        other
        for other in hass.config_entries.async_entries(DOMAIN)
        if other.entry_id != entry.entry_id
    ]
    if not remaining:
        await async_uninstall_blueprints(hass)
        await async_uninstall_theme(hass)
        async_unload_services(hass)


async def async_reload_entry(hass: HomeAssistant, entry: OptieFamilyConfigEntry) -> None:
    """Recharge l'entrée quand les options changent."""
    await hass.config_entries.async_reload(entry.entry_id)
