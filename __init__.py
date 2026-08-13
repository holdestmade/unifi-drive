"""The UniFi Drive integration."""
from __future__ import annotations

import asyncio
import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import (
    DEFAULT_TIMEOUT,
    UniFiDriveAuthError,
    UniFiDriveClient,
    UniFiDriveError,
    UniFiDriveRateLimitError,
)
from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import UniFiDriveConfigEntry, UnifiDriveCoordinator
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions once, at startup."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: UniFiDriveConfigEntry) -> bool:
    data = entry.data
    verify_ssl = data.get(CONF_VERIFY_SSL, False)
    scan = entry.options.get(
        CONF_SCAN_INTERVAL, data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )

    # UniFi OS sets cookies against a bare IP, hence the unsafe cookie jar.
    session = async_create_clientsession(
        hass,
        verify_ssl=verify_ssl,
        cookie_jar=aiohttp.CookieJar(unsafe=True),
        timeout=DEFAULT_TIMEOUT,
    )
    client = UniFiDriveClient(data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD], session)

    try:
        await client.login()
        coordinator = UnifiDriveCoordinator(hass, entry, client, scan)
        await coordinator.async_config_entry_first_refresh()
    except UniFiDriveRateLimitError as exc:
        await client.close()
        _LOGGER.warning("UniFi Drive login rate-limited; deferring setup: %s", exc)
        raise ConfigEntryNotReady(str(exc)) from exc
    except UniFiDriveAuthError as exc:
        await client.close()
        raise ConfigEntryAuthFailed(str(exc)) from exc
    except (ConfigEntryAuthFailed, ConfigEntryNotReady):
        await client.close()
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError, UniFiDriveError) as exc:
        await client.close()
        raise ConfigEntryNotReady(f"Cannot connect to UniFi Drive: {exc}") from exc

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries.

    Version 1 allowed credentials to live in ``entry.options``; version 2 keeps
    connection settings in ``entry.data`` and only ``scan_interval`` in options.
    """
    if entry.version > 2:
        return False

    if entry.version == 1:
        data = dict(entry.data)
        options = dict(entry.options)
        for key in (CONF_HOST, CONF_USERNAME, CONF_PASSWORD, CONF_VERIFY_SSL):
            if key in options:
                data[key] = options.pop(key)
        # Options take precedence over data for the scan interval; strip it
        # from data either way.
        scan = options.pop(CONF_SCAN_INTERVAL, data.pop(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        options[CONF_SCAN_INTERVAL] = scan
        hass.config_entries.async_update_entry(entry, data=data, options=options, version=2)

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: UniFiDriveConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.close()
    return unload_ok
