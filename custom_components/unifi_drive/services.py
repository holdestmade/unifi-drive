"""Actions for the UniFi Drive integration."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import UniFiDriveError
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_EXTRA_PATHS,
    ATTR_OUTPUT_DIR,
    DEFAULT_DUMP_DIR,
    DOMAIN,
    SERVICE_DUMP_API,
)
from .dump import async_dump_api

DUMP_API_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_OUTPUT_DIR, default=DEFAULT_DUMP_DIR): cv.string,
        vol.Optional(ATTR_EXTRA_PATHS, default=list): vol.All(
            cv.ensure_list, [cv.string]
        ),
    }
)


def _resolve_entry(hass: HomeAssistant, entry_id: str | None) -> ConfigEntry:
    """Return the config entry to dump, or explain why it can't be picked."""
    if entry_id is not None:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                f"No UniFi Drive config entry with ID {entry_id}"
            )
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                f"The UniFi Drive config entry {entry.title} is not loaded"
            )
        return entry

    loaded = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if not loaded:
        raise ServiceValidationError("No loaded UniFi Drive config entry")
    if len(loaded) > 1:
        raise ServiceValidationError(
            "Several UniFi Drive config entries are loaded; pass config_entry_id "
            "to choose one"
        )
    return loaded[0]


def _resolve_output_dir(hass: HomeAssistant, output_dir: str) -> Path:
    """Resolve ``output_dir`` to a directory below the config directory.

    Uses pure path arithmetic so no blocking filesystem call happens in the
    event loop.  Absolute paths and ``..`` escapes normalise to somewhere
    outside the config directory and are rejected, as is the config directory
    itself — the dump wants a folder of its own.
    """
    config_dir = Path(os.path.normpath(hass.config.path()))
    target = Path(os.path.normpath(hass.config.path(output_dir)))
    if config_dir not in target.parents:
        raise ServiceValidationError(
            "output_dir must be a directory inside the configuration directory: "
            f"{output_dir}"
        )
    return target


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions."""

    async def async_dump_api_service(call: ServiceCall) -> ServiceResponse:
        """Write the raw controller responses to JSON files."""
        entry = _resolve_entry(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        out_dir = _resolve_output_dir(hass, call.data[ATTR_OUTPUT_DIR])
        coordinator = entry.runtime_data

        try:
            result: dict[str, Any] = await async_dump_api(
                hass,
                coordinator.client,
                out_dir,
                call.data[ATTR_EXTRA_PATHS],
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise HomeAssistantError(f"Cannot reach UniFi Drive: {err}") from err
        except UniFiDriveError as err:
            raise HomeAssistantError(f"UniFi Drive API error: {err}") from err
        except OSError as err:
            raise HomeAssistantError(f"Cannot write to {out_dir}: {err}") from err

        return result

    hass.services.async_register(
        DOMAIN,
        SERVICE_DUMP_API,
        async_dump_api_service,
        schema=DUMP_API_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
