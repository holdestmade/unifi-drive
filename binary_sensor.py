from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UnifiDriveCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: UnifiDriveCoordinator = data["coordinator"]

    entities: list[BinarySensorEntity] = []

    entities.append(ActiveNICConnectedBinarySensor(coordinator, entry))

    drives = (coordinator.data or {}).get("drives") or {}
    drive_items = drives.get("drives") if isinstance(drives, dict) else []
    for d in drive_items or []:
        did = d.get("id")
        name = d.get("name") or did or "Drive"
        if not did:
            continue
        entities.append(DriveSnapshotEnabledBinary(coordinator, entry, did, name))

    async_add_entities(entities)


class _BaseUDBinary(CoordinatorEntity[UnifiDriveCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: UnifiDriveCoordinator, entry: ConfigEntry, name_suffix: str, icon: Optional[str] = None) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._name_suffix = name_suffix
        self._attr_unique_id = f"{entry.entry_id}_{name_suffix}"
        self._attr_icon = icon

    @property
    def device_info(self) -> DeviceInfo:
        dev = (self.coordinator.data or {}).get("device") or {}
        model = dev.get("model") or "UNAS"
        name = dev.get("name") or "UniFi Drive"
        sw = dev.get("firmwareVersion") or dev.get("version")
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            manufacturer="Ubiquiti",
            model=model,
            name=name,
            sw_version=sw,
        )


class ActiveNICConnectedBinarySensor(_BaseUDBinary):
    _attr_name = "Active NIC Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:ethernet"
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "nic_connected_bin", "mdi:ethernet")
    @staticmethod
    def _pick_nic(dev: dict) -> Optional[dict]:
        nics = dev.get("networkInterfaces") or []
        if not isinstance(nics, list):
            return None
        for n in nics:
            try:
                if n.get("connected"):
                    return n
            except Exception:
                continue
        return nics[0] if nics else None
    @property
    def is_on(self) -> bool | None:
        dev = (self.coordinator.data or {}).get("device") or {}
        nic = self._pick_nic(dev)
        return bool(nic and nic.get("connected"))
    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        dev = (self.coordinator.data or {}).get("device") or {}
        nic = self._pick_nic(dev)
        if not nic:
            return None
        return {
            "interface": nic.get("interface"),
            "interface_name": nic.get("interfaceName"),
            "address": nic.get("address"),
            "mac": nic.get("mac"),
            "link_speed": nic.get("linkSpeed"),
        }


def _drives_list(coordinator: UnifiDriveCoordinator) -> list[dict[str, Any]]:
    drives = (coordinator.data or {}).get("drives") or {}
    return drives.get("drives") if isinstance(drives, dict) else []


class _BaseDriveBinary(_BaseUDBinary):
    def __init__(self, coordinator, entry, drive_id: str, drive_name: str, suffix: str, icon: Optional[str] = None):
        super().__init__(coordinator, entry, f"drive_{drive_id}_{suffix}", icon)
        self._drive_id = drive_id
        self._drive_name = drive_name
    @property
    def name(self) -> str | None:
        return f"{self._drive_name} {self._attr_name}" if self._attr_name else self._drive_name
    def _find_drive(self) -> dict[str, Any] | None:
        for d in _drives_list(self.coordinator) or []:
            if d.get("id") == self._drive_id:
                return d
        return None


class DriveSnapshotEnabledBinary(_BaseDriveBinary):
    _attr_name = "Snapshot Enabled"
    _attr_icon = "mdi:camera-burst"
    def __init__(self, coordinator, entry, drive_id, drive_name):
        super().__init__(coordinator, entry, drive_id, drive_name, "snapshot_enabled_bin", "mdi:camera-burst")
    @property
    def is_on(self) -> bool | None:
        d = self._find_drive() or {}
        prot = d.get("protections") or {}
        val = prot.get("snapshotEnabled")
        return bool(val)
    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        d = self._find_drive() or {}
        return {
            "type": d.get("type"),
            "status": d.get("status"),
            "storage_pool_id": d.get("storagePoolId"),
        }
