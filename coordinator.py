"""Coordinator and data normalisation for UniFi Drive."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import UniFiDriveAuthError, UniFiDriveClient, UniFiDriveError
from .const import DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

UniFiDriveConfigEntry = ConfigEntry["UnifiDriveCoordinator"]


@dataclass(slots=True)
class UniFiDriveData:
    """Normalised UniFi Drive data consumed by the entities."""

    device: dict[str, Any]
    storage: dict[str, Any]
    fan_control: dict[str, Any]
    drives_by_id: dict[str, dict[str, Any]]
    disks_by_key: dict[str, dict[str, Any]]
    shares_count: int
    storage_total_bytes: int
    storage_used_bytes: int
    storage_free_bytes: int


def disk_key(disk: dict[str, Any]) -> str:
    """Return a stable identifier for a disk (serial, falling back to slot)."""
    return disk.get("serial") or f"slot{disk.get('slotId', '?')}"


def pick_active_nic(device: dict[str, Any]) -> dict[str, Any] | None:
    """Return the connected NIC, falling back to the first one."""
    nics = device.get("networkInterfaces")
    if not isinstance(nics, list) or not nics:
        return None
    for nic in nics:
        if isinstance(nic, dict) and nic.get("connected"):
            return nic
    return nics[0] if isinstance(nics[0], dict) else None


def _storage_totals(
    storage: dict[str, Any], volumes: Any, device: dict[str, Any]
) -> tuple[int, int, int]:
    """Compute (total, used, free) bytes from the best available source."""
    pools = storage.get("pools")
    if isinstance(pools, list) and pools:
        try:
            total = sum(float(p.get("capacity") or 0) for p in pools)
            used = sum(float(p.get("usage") or 0) for p in pools)
        except (TypeError, ValueError):
            pass
        else:
            return int(total), int(used), int(max(0.0, total - used))

    if volumes:
        if isinstance(volumes, list):
            items = volumes
        elif isinstance(volumes, dict):
            items = volumes.get("items") or []
        else:
            items = []
        total = used = free = 0.0
        for vol in items:
            if not isinstance(vol, dict):
                continue
            try:
                size = float(vol.get("sizeBytes") or vol.get("size") or 0)
                vol_used = float(vol.get("usedBytes") or vol.get("used") or 0)
                avail = float(
                    vol.get("availableBytes")
                    or vol.get("free")
                    or (size - vol_used if size and vol_used else 0)
                )
            except (TypeError, ValueError):
                continue
            total += size
            used += vol_used
            free += avail
        if total or used or free:
            return int(total), int(used), int(free)

    storage_list = device.get("storage")
    if isinstance(storage_list, list):
        raid = next((s for s in storage_list if s.get("type") == "raid"), None)
        if raid and all(k in raid for k in ("size", "used", "avail")):
            try:
                return int(float(raid["size"])), int(float(raid["used"])), int(float(raid["avail"]))
            except (TypeError, ValueError):
                pass

    return 0, 0, 0


def _process_data(raw: dict[str, Any]) -> UniFiDriveData:
    """Normalise the raw endpoint payloads once per update."""
    device = raw.get("device") if isinstance(raw.get("device"), dict) else {}
    storage = raw.get("storage") if isinstance(raw.get("storage"), dict) else {}
    fan_control = raw.get("fan_control") if isinstance(raw.get("fan_control"), dict) else {}

    drives_raw = raw.get("drives")
    drive_items = drives_raw.get("drives") if isinstance(drives_raw, dict) else None
    drives_by_id = {
        d["id"]: d for d in drive_items or [] if isinstance(d, dict) and d.get("id")
    }

    disks = [
        d
        for d in storage.get("disks") or []
        if isinstance(d, dict) and (d.get("state") or "").lower() != "empty"
    ]
    disks_by_key = {disk_key(d): d for d in disks}

    shares = raw.get("shares")
    if isinstance(shares, list):
        shares_count = len(shares)
    elif isinstance(shares, dict):
        shares_count = len(shares.get("items") or [])
    else:
        shares_count = 0

    total, used, free = _storage_totals(storage, raw.get("volumes"), device)

    return UniFiDriveData(
        device=device,
        storage=storage,
        fan_control=fan_control,
        drives_by_id=drives_by_id,
        disks_by_key=disks_by_key,
        shares_count=shares_count,
        storage_total_bytes=total,
        storage_used_bytes=used,
        storage_free_bytes=free,
    )


class UnifiDriveCoordinator(DataUpdateCoordinator[UniFiDriveData]):
    """Polling coordinator for UniFi Drive with auto reauth/refresh."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: UniFiDriveClient,
        scan_interval: int | None,
    ) -> None:
        if not scan_interval or scan_interval <= 0:
            scan_interval = DEFAULT_SCAN_INTERVAL
        super().__init__(
            hass,
            logger=_LOGGER,
            config_entry=entry,
            name="UniFi Drive Coordinator",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client

    async def _async_update_data(self) -> UniFiDriveData:
        try:
            raw = await self.client.get_all()
        except UniFiDriveAuthError as err:
            # If we genuinely can't auth after retry, surface reauth
            raise ConfigEntryAuthFailed(str(err)) from err
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise UpdateFailed(f"Connection error: {err}") from err
        except UniFiDriveError as err:
            raise UpdateFailed(str(err)) from err
        return _process_data(raw)
