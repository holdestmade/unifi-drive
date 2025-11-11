from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed

from .api import UniFiDriveClient
from .const import DOMAIN, DEFAULT_SCAN_INTERVAL


class UnifiDriveCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polling coordinator for UniFi Drive with auto reauth/refresh."""

    def __init__(self, hass: HomeAssistant, client: UniFiDriveClient, scan_interval: int | None) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(f"{DOMAIN}.coordinator"),
            name="UniFi Drive Coordinator",
            update_interval=timedelta(seconds=scan_interval or DEFAULT_SCAN_INTERVAL),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            # `get_all` now ensures authentication and retries 401s once
            return await self.client.get_all()
        except RuntimeError as err:
            msg = str(err)
            # If we genuinely can't auth after retry, surface reauth
            if "HTTP 401" in msg or "Unauthorized" in msg or "AUTH_FAILED" in msg:
                raise ConfigEntryAuthFailed from err
            raise UpdateFailed(msg) from err
