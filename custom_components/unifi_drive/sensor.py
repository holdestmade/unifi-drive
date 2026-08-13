"""Sensor platform for UniFi Drive."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import (
    UniFiDriveConfigEntry,
    UniFiDriveData,
    UnifiDriveCoordinator,
    pick_active_nic,
)
from .entity import UniFiDriveEntity


def _kib_to_bytes(val: Any) -> int | None:
    try:
        return int(float(val) * 1024)
    except (TypeError, ValueError):
        return None


def _maybe_int(val: Any) -> int | None:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def _cpu_load(data: UniFiDriveData) -> float | None:
    load = (data.device.get("cpu") or {}).get("currentload")
    try:
        load = float(load)
    except (TypeError, ValueError):
        return None
    return round(load * 100.0, 2) if load <= 1 else round(load, 2)


def _cpu_temperature(data: UniFiDriveData) -> float | None:
    temp = (data.device.get("cpu") or {}).get("temperature")
    try:
        return round(float(temp), 1)
    except (TypeError, ValueError):
        return None


def _memory_bytes(key: str) -> Callable[[UniFiDriveData], int | None]:
    def _value(data: UniFiDriveData) -> int | None:
        mem = data.device.get("memory")
        if not isinstance(mem, dict) or mem.get(key) is None:
            return None
        return _kib_to_bytes(mem.get(key))

    return _value


def _memory_total_available(data: UniFiDriveData) -> tuple[int, int] | None:
    mem = data.device.get("memory") or {}
    total = _maybe_int(mem.get("total"))
    avail = _maybe_int(mem.get("available"))
    if avail is None:
        avail = _maybe_int(mem.get("free"))
    if not total or total <= 0 or avail is None:
        return None
    return total, avail


def _memory_usage_percent(data: UniFiDriveData) -> float | None:
    totals = _memory_total_available(data)
    if totals is None:
        return None
    total, avail = totals
    pct = ((total - avail) / total) * 100.0
    return round(max(0.0, min(100.0, pct)), 1)


def _memory_used_bytes(data: UniFiDriveData) -> int | None:
    totals = _memory_total_available(data)
    if totals is None:
        return None
    total, avail = totals
    return _kib_to_bytes(max(0, total - avail))


def _parse_speed_mbps(text: Any) -> int | None:
    if not text:
        return None
    s = str(text).lower()
    if "gb" in s:
        for part in s.replace("fdx", "").replace("gbps", "").replace("gbe", "").split():
            try:
                return int(float(part) * 1000)
            except ValueError:
                continue
    for tok in s.split():
        try:
            return int(float(tok))
        except ValueError:
            continue
    return None


def _nic_speed(data: UniFiDriveData) -> int | None:
    nic = pick_active_nic(data.device)
    return _parse_speed_mbps(nic.get("linkSpeed")) if nic else None


def _fan_profile_options(data: UniFiDriveData) -> list[str] | None:
    fan = data.fan_control
    options = {p for p in fan.get("availableProfiles") or [] if isinstance(p, str)}
    current = fan.get("currentProfile")
    if isinstance(current, str):
        options.add(current)
    return sorted(options) or None


def _storage_used_percent(data: UniFiDriveData) -> float | None:
    if data.storage_total_bytes <= 0:
        return None
    return round((data.storage_used_bytes / data.storage_total_bytes) * 100.0, 1)


def _hottest_disk_temperature(data: UniFiDriveData) -> float | int | None:
    temps = [
        d.get("temperature")
        for d in data.disks_by_key.values()
        if isinstance(d.get("temperature"), (int, float))
    ]
    return max(temps) if temps else None


def _disk_state_options(data: UniFiDriveData) -> list[str] | None:
    options = {(d.get("state") or "").lower() for d in data.disks_by_key.values()}
    options.discard("")
    return sorted(options) or None


@dataclass(frozen=True, kw_only=True)
class UniFiDriveSensorDescription(SensorEntityDescription):
    """Describes a UniFi Drive sensor with a value derived from the data set."""

    value_fn: Callable[[UniFiDriveData], StateType]
    options_fn: Callable[[UniFiDriveData], list[str] | None] | None = None


@dataclass(frozen=True, kw_only=True)
class UniFiDriveItemSensorDescription(SensorEntityDescription):
    """Describes a sensor whose value comes from a single drive/disk dict."""

    value_fn: Callable[[dict[str, Any]], StateType]
    options_fn: Callable[[UniFiDriveData], list[str] | None] | None = None


SENSORS: tuple[UniFiDriveSensorDescription, ...] = (
    UniFiDriveSensorDescription(
        key="device_firmwareVersion",
        name="Firmware Version",
        icon="mdi:nas",
        value_fn=lambda data: data.device.get("firmwareVersion"),
    ),
    UniFiDriveSensorDescription(
        key="device_version",
        name="Drive App Version",
        icon="mdi:information-outline",
        value_fn=lambda data: data.device.get("version"),
    ),
    UniFiDriveSensorDescription(
        key="device_status",
        name="System Status",
        icon="mdi:checkbox-marked-circle-outline",
        value_fn=lambda data: data.device.get("status"),
    ),
    UniFiDriveSensorDescription(
        key="cpu_load",
        name="CPU Load",
        icon="mdi:cpu-64-bit",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_cpu_load,
    ),
    UniFiDriveSensorDescription(
        key="cpu_temp",
        name="CPU Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_cpu_temperature,
    ),
    UniFiDriveSensorDescription(
        key="device_memory_total",
        name="Memory Total",
        icon="mdi:memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_memory_bytes("total"),
    ),
    UniFiDriveSensorDescription(
        key="device_memory_available",
        name="Memory Available",
        icon="mdi:memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_memory_bytes("available"),
    ),
    UniFiDriveSensorDescription(
        key="device_memory_free",
        name="Memory Free",
        icon="mdi:memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_memory_bytes("free"),
    ),
    UniFiDriveSensorDescription(
        key="memory_usage_percent",
        name="Memory Usage",
        icon="mdi:memory",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_memory_usage_percent,
    ),
    UniFiDriveSensorDescription(
        key="memory_used_bytes",
        name="Memory Used",
        icon="mdi:memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_memory_used_bytes,
    ),
    UniFiDriveSensorDescription(
        key="nic_speed",
        name="Active NIC Link Speed",
        icon="mdi:lan",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_nic_speed,
    ),
    UniFiDriveSensorDescription(
        key="fan_profile",
        name="Fan Profile",
        icon="mdi:fan",
        device_class=SensorDeviceClass.ENUM,
        value_fn=lambda data: data.fan_control.get("currentProfile"),
        options_fn=_fan_profile_options,
    ),
    UniFiDriveSensorDescription(
        key="storage_total_bytes",
        name="Storage Total",
        icon="mdi:database",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.storage_total_bytes or None,
    ),
    UniFiDriveSensorDescription(
        key="storage_used_bytes",
        name="Storage Used",
        icon="mdi:database",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.storage_used_bytes or None,
    ),
    UniFiDriveSensorDescription(
        key="storage_free_bytes",
        name="Storage Free",
        icon="mdi:database",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.storage_free_bytes or None,
    ),
    UniFiDriveSensorDescription(
        key="storage_used_percent",
        name="Storage Used Percent",
        icon="mdi:database-percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_storage_used_percent,
    ),
    UniFiDriveSensorDescription(
        key="shares_count",
        name="Shares Count",
        icon="mdi:folder-multiple",
        value_fn=lambda data: data.shares_count,
    ),
    UniFiDriveSensorDescription(
        key="disks_count",
        name="Disks Count",
        icon="mdi:harddisk",
        value_fn=lambda data: len(data.disks_by_key),
    ),
    UniFiDriveSensorDescription(
        key="hottest_disk_temp",
        name="Hottest Disk Temperature",
        icon="mdi:thermometer-water",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_hottest_disk_temperature,
    ),
)


def _drive_usage_bytes(drive: dict[str, Any]) -> int | None:
    try:
        return int(drive.get("usage", 0))
    except (TypeError, ValueError):
        return None


DRIVE_SENSORS: tuple[UniFiDriveItemSensorDescription, ...] = (
    UniFiDriveItemSensorDescription(
        key="usage_bytes",
        name="Usage",
        icon="mdi:database",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_drive_usage_bytes,
    ),
    UniFiDriveItemSensorDescription(
        key="status",
        name="Status",
        icon="mdi:checkbox-marked-circle-outline",
        value_fn=lambda drive: drive.get("status")
        if isinstance(drive.get("status"), str)
        else None,
    ),
    UniFiDriveItemSensorDescription(
        key="member_count",
        name="Member Count",
        icon="mdi:account-multiple",
        value_fn=lambda drive: drive.get("memberCount"),
    ),
)


def _disk_temperature(disk: dict[str, Any]) -> float | None:
    temp = disk.get("temperature")
    return round(float(temp), 1) if isinstance(temp, (int, float)) else None


def _disk_capacity(disk: dict[str, Any]) -> int | None:
    size = disk.get("size")
    try:
        return int(size) if size is not None else None
    except (TypeError, ValueError):
        return None


def _disk_int(key: str) -> Callable[[dict[str, Any]], int | None]:
    def _value(disk: dict[str, Any]) -> int | None:
        val = disk.get(key)
        return int(val) if isinstance(val, (int, float)) else None

    return _value


def _disk_read_error_rate(disk: dict[str, Any]) -> int | None:
    val = disk.get("readErrorRate")
    if val is None:
        val = disk.get("smartReadErrorCount")
    return int(val) if isinstance(val, (int, float)) else None


def _disk_state(disk: dict[str, Any]) -> str | None:
    return (disk.get("state") or "").lower() or None


DISK_SENSORS: tuple[UniFiDriveItemSensorDescription, ...] = (
    UniFiDriveItemSensorDescription(
        key="temp",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_disk_temperature,
    ),
    UniFiDriveItemSensorDescription(
        key="capacity_bytes",
        name="Capacity",
        icon="mdi:harddisk",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_disk_capacity,
    ),
    UniFiDriveItemSensorDescription(
        key="rpm",
        name="RPM",
        icon="mdi:rotate-right",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_disk_int("rpm"),
    ),
    UniFiDriveItemSensorDescription(
        key="state",
        name="State",
        icon="mdi:checkbox-marked-circle-outline",
        device_class=SensorDeviceClass.ENUM,
        value_fn=_disk_state,
        options_fn=_disk_state_options,
    ),
    UniFiDriveItemSensorDescription(
        key="power_on_hours",
        name="Power On",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_disk_int("powerOnHours"),
    ),
    UniFiDriveItemSensorDescription(
        key="smart_bad_sectors",
        name="SMART Bad Sectors",
        icon="mdi:alert-decagram",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_disk_int("badSectorCount"),
    ),
    UniFiDriveItemSensorDescription(
        key="smart_uncorrectable",
        name="SMART Uncorrectable",
        icon="mdi:alert",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_disk_int("uncorrectableSectorCount"),
    ),
    UniFiDriveItemSensorDescription(
        key="read_error_rate",
        name="Read Error Rate",
        icon="mdi:chart-line",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_disk_read_error_rate,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UniFiDriveConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data

    async_add_entities(UniFiDriveSensor(coordinator, description) for description in SENSORS)

    known_drives: set[str] = set()
    known_disks: set[str] = set()

    @callback
    def _add_item_entities() -> None:
        """Add entities for drives/disks that appeared since the last update."""
        data = coordinator.data
        new_entities: list[SensorEntity] = []
        for drive_id, drive in data.drives_by_id.items():
            if drive_id in known_drives:
                continue
            known_drives.add(drive_id)
            drive_name = drive.get("name") or drive_id
            new_entities.extend(
                UniFiDriveDriveSensor(coordinator, description, drive_id, drive_name)
                for description in DRIVE_SENSORS
            )
        for key, disk in data.disks_by_key.items():
            if key in known_disks:
                continue
            known_disks.add(key)
            new_entities.extend(
                UniFiDriveDiskSensor(coordinator, description, key, disk)
                for description in DISK_SENSORS
            )
        if new_entities:
            async_add_entities(new_entities)

    _add_item_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_item_entities))


class UniFiDriveSensorBase(UniFiDriveEntity, SensorEntity):
    """Base sensor that keeps dynamic ENUM options in sync."""

    def __init__(
        self,
        coordinator: UnifiDriveCoordinator,
        unique_suffix: str,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, unique_suffix)
        self.entity_description = description
        self._update_options()

    def _update_options(self) -> None:
        options_fn = getattr(self.entity_description, "options_fn", None)
        if options_fn is not None:
            self._attr_options = options_fn(self.coordinator.data)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_options()
        super()._handle_coordinator_update()


class UniFiDriveSensor(UniFiDriveSensorBase):
    """Sensor deriving its value from the full coordinator data set."""

    entity_description: UniFiDriveSensorDescription

    def __init__(
        self, coordinator: UnifiDriveCoordinator, description: UniFiDriveSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key, description)

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data)


class UniFiDriveDriveSensor(UniFiDriveSensorBase):
    """Sensor for a single UniFi Drive (share/team drive)."""

    entity_description: UniFiDriveItemSensorDescription

    def __init__(
        self,
        coordinator: UnifiDriveCoordinator,
        description: UniFiDriveItemSensorDescription,
        drive_id: str,
        drive_name: str,
    ) -> None:
        super().__init__(coordinator, f"drive_{drive_id}_{description.key}", description)
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
    def native_value(self) -> StateType:
        drive = self._drive
        return self.entity_description.value_fn(drive) if drive else None


class UniFiDriveDiskSensor(UniFiDriveSensorBase):
    """Sensor for a single physical disk."""

    entity_description: UniFiDriveItemSensorDescription

    def __init__(
        self,
        coordinator: UnifiDriveCoordinator,
        description: UniFiDriveItemSensorDescription,
        disk_key: str,
        disk: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, f"disk_{disk_key}_{description.key}", description)
        self._disk_key = disk_key
        self._slot = str(disk.get("slotId") or "?")
        self._model = disk.get("model") or "Disk"

    @property
    def _disk(self) -> dict[str, Any] | None:
        return self.coordinator.data.disks_by_key.get(self._disk_key)

    @property
    def name(self) -> str:
        disk = self._disk or {}
        slot = str(disk.get("slotId") or self._slot)
        model = disk.get("model") or self._model
        return f"Disk {slot} ({model}) {self.entity_description.name}"

    @property
    def native_value(self) -> StateType:
        disk = self._disk
        return self.entity_description.value_fn(disk) if disk else None
