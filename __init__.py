from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import ConfigEntryNotReady, ConfigEntryAuthFailed

from .api import UniFiDriveClient
from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_VERIFY_SSL,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)
from .coordinator import UnifiDriveCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = entry.options.get(CONF_HOST, entry.data[CONF_HOST])
    user = entry.options.get(CONF_USERNAME, entry.data[CONF_USERNAME])
    pwd = entry.options.get(CONF_PASSWORD, entry.data[CONF_PASSWORD])
    verify_ssl = entry.options.get(CONF_VERIFY_SSL, entry.data.get(CONF_VERIFY_SSL, False))
    scan = entry.options.get(CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    client = UniFiDriveClient(host, user, pwd, verify_ssl=verify_ssl)

    try:
        await client.login()
        coordinator = UnifiDriveCoordinator(hass, client, scan)
        await coordinator.async_config_entry_first_refresh()
    except RuntimeError as exc:
        await client.close()
        msg = str(exc)
        if msg.startswith("RATE_LIMIT:") or "HTTP 429" in msg:
            _LOGGER.warning("UniFi Drive login rate-limited; deferring setup. Details: %s", msg)
            raise ConfigEntryNotReady from exc
        if "AUTH_FAILED" in msg or "HTTP 401" in msg or "Unauthorized" in msg:
            _LOGGER.error("UniFi Drive authentication failed: %s", msg)
            raise ConfigEntryAuthFailed from exc
        _LOGGER.error("UniFi Drive login failed: %s", msg)
        raise ConfigEntryNotReady from exc

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"client": client, "coordinator": coordinator}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data and data.get("client"):
        try:
            await data["client"].close()
        except Exception:
            _LOGGER.debug("Error closing UniFi Drive client session", exc_info=True)
    return unload_ok
