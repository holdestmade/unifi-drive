"""Binary sensor platform for UniFi Drive."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import (
    UniFiDriveConfigEntry,
    UniFiDriveData,
    UnifiDriveCoordinator,
    pick_active_nic,
)
from .entity import UniFiDriveEntity


def _nic_is_on(data: UniFiDriveData) -> bool:
    nic = pick_active_nic(data.device)
    return bool(nic and nic.get("connected"))


def _nic_attributes(data: UniFiDriveData) -> dict[str, Any] | None:
    nic = pick_active_nic(data.device)
    if not nic:
        return None
    return {
        "interface": nic.get("interface"),
        "interface_name": nic.get("interfaceName"),
        "address": nic.get("address"),
        "mac": nic.get("mac"),
        "link_speed": nic.get("linkSpeed"),
    }


@dataclass(frozen=True, kw_only=True)
class UniFiDriveBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a UniFi Drive binary sensor derived from the data set."""

    is_on_fn: Callable[[UniFiDriveData], bool | None]
    attributes_fn: Callable[[UniFiDriveData], dict[str, Any] | None] | None = None


@dataclass(frozen=True, kw_only=True)
class UniFiDriveDriveBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a binary sensor derived from a single drive dict."""

    is_on_fn: Callable[[dict[str, Any]], bool | None]
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None


BINARY_SENSORS: tuple[UniFiDriveBinarySensorDescription, ...] = (
    UniFiDriveBinarySensorDescription(
        key="nic_connected_bin",
        name="Active NIC Connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:ethernet",
        is_on_fn=_nic_is_on,
        attributes_fn=_nic_attributes,
    ),
)

DRIVE_BINARY_SENSORS: tuple[UniFiDriveDriveBinarySensorDescription, ...] = (
    UniFiDriveDriveBinarySensorDescription(
        key="snapshot_enabled_bin",
        name="Snapshot Enabled",
        icon="mdi:camera-burst",
        is_on_fn=lambda drive: bool((drive.get("protections") or {}).get("snapshotEnabled")),
        attributes_fn=lambda drive: {
            "type": drive.get("type"),
            "status": drive.get("status"),
            "storage_pool_id": drive.get("storagePoolId"),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UniFiDriveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data

    async_add_entities(
        UniFiDriveBinarySensor(coordinator, description) for description in BINARY_SENSORS
    )

    known_drives: set[str] = set()

    @callback
    def _add_drive_entities() -> None:
        """Add entities for drives that appeared since the last update."""
        new_entities: list[BinarySensorEntity] = []
        for drive_id, drive in coordinator.data.drives_by_id.items():
            if drive_id in known_drives:
                continue
            known_drives.add(drive_id)
            drive_name = drive.get("name") or drive_id
            new_entities.extend(
                UniFiDriveDriveBinarySensor(coordinator, description, drive_id, drive_name)
                for description in DRIVE_BINARY_SENSORS
            )
        if new_entities:
            async_add_entities(new_entities)

    _add_drive_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_drive_entities))


class UniFiDriveBinarySensor(UniFiDriveEntity, BinarySensorEntity):
    """Binary sensor deriving its state from the full coordinator data set."""

    entity_description: UniFiDriveBinarySensorDescription

    def __init__(
        self,
        coordinator: UnifiDriveCoordinator,
        description: UniFiDriveBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.is_on_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)


class UniFiDriveDriveBinarySensor(UniFiDriveEntity, BinarySensorEntity):
    """Binary sensor for a single UniFi Drive."""

    entity_description: UniFiDriveDriveBinarySensorDescription

    def __init__(
        self,
        coordinator: UnifiDriveCoordinator,
        description: UniFiDriveDriveBinarySensorDescription,
        drive_id: str,
        drive_name: str,
    ) -> None:
        super().__init__(coordinator, f"drive_{drive_id}_{description.key}")
        self.entity_description = description
        self._drive_id = drive_id
        self._drive_name = drive_name

    @property
    def _drive(self) -> dict[str, Any] | None:
        return self.coordinator.data.drives_by_id.get(self._drive_id)

    @property
    def name(self) -> str:
        drive_name = (self._drive or {}).get("name") or self._drive_name
        return f"{drive_name} {self.entity_description.name}"

    @property
    def is_on(self) -> bool | None:
        drive = self._drive
        return self.entity_description.is_on_fn(drive) if drive else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        drive = self._drive
        if drive is None or self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(drive)
