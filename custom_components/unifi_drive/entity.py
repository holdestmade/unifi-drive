"""Shared entity base class for UniFi Drive."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UnifiDriveCoordinator


class UniFiDriveEntity(CoordinatorEntity[UnifiDriveCoordinator]):
    """Base entity tied to the UniFi Drive coordinator and device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: UnifiDriveCoordinator, unique_suffix: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{unique_suffix}"

    @property
    def device_info(self) -> DeviceInfo:
        dev = self.coordinator.data.device
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            manufacturer="Ubiquiti",
            model=dev.get("model") or "UNAS",
            name=dev.get("name") or "UniFi Drive",
            sw_version=dev.get("firmwareVersion") or dev.get("version"),
        )
