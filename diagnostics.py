"""Diagnostics support for UniFi Drive.

Returns the raw payload of every controller call the integration makes, with
identifying values redacted, so a diagnostics file is safe to attach to an
issue.  The ``unifi_drive.dump_api`` action covers more endpoints and writes
unredacted files for local reference.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, CONF_VERIFY_SSL
from .coordinator import UniFiDriveConfigEntry
from .redact import REDACTED, redact_payload


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: UniFiDriveConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data

    processed = asdict(coordinator.data) if coordinator.data else {}

    return {
        "entry": {
            "version": entry.version,
            "host": REDACTED if entry.data.get(CONF_HOST) else None,
            "username": REDACTED if entry.data.get(CONF_USERNAME) else None,
            "password": REDACTED if entry.data.get(CONF_PASSWORD) else None,
            "verify_ssl": entry.data.get(CONF_VERIFY_SSL, False),
            "options": dict(entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
        },
        # Exactly what the controller returned on the last poll, per endpoint.
        "raw": redact_payload(coordinator.last_raw),
        # The normalised view the entities are built from.
        "processed": redact_payload(processed),
    }
