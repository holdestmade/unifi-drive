from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfTemperature,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTime,
    PERCENTAGE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from .coordinator import UnifiDriveCoordinator


def _kib_to_bytes(val: Any) -> Optional[int]:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    return int(v * 1024)


def _maybe_int(val: Any) -> Optional[int]:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: UnifiDriveCoordinator = data["coordinator"]

    entities: list[SensorEntity] = []

    entities.extend(
        [
            SimpleTextSensor(coordinator, entry, ("device", "firmwareVersion"), "Firmware Version", "mdi:nas"),
            SimpleTextSensor(coordinator, entry, ("device", "version"), "Drive App Version", "mdi:information-outline"),
            SimpleTextSensor(coordinator, entry, ("device", "status"), "System Status", "mdi:checkbox-marked-circle-outline"),
            CpuLoadSensor(coordinator, entry),
            CpuTempSensor(coordinator, entry),
            MemBytesSensor(coordinator, entry, ("device", "memory", "total"), "Memory Total"),
            MemBytesSensor(coordinator, entry, ("device", "memory", "available"), "Memory Available"),
            MemBytesSensor(coordinator, entry, ("device", "memory", "free"), "Memory Free"),
            MemUsagePercentSensor(coordinator, entry),
            MemUsedBytesSensor(coordinator, entry),
            ActiveNicSpeedSensor(coordinator, entry),
            FanProfileSensor(coordinator, entry),
        ]
    )

    entities.extend(
        [
            StorageTotalBytesSensor(coordinator, entry),
            StorageUsedBytesSensor(coordinator, entry),
            StorageFreeBytesSensor(coordinator, entry),
            StorageUsedPercentSensor(coordinator, entry),
            SharesCountSensor(coordinator, entry),
            DisksCountSensor(coordinator, entry),
            HottestDiskTempSensor(coordinator, entry),
        ]
    )

    drives = (coordinator.data or {}).get("drives") or {}
    drive_items = drives.get("drives") if isinstance(drives, dict) else []
    for d in drive_items or []:
        did = d.get("id")
        name = d.get("name") or did or "Drive"
        if not did:
            continue
        entities.extend(
            [
                DriveUsageBytesSensor(coordinator, entry, did, name),
                DriveStatusEnumSensor(coordinator, entry, did, name),
                DriveMemberCountSensor(coordinator, entry, did, name),
            ]
        )

    for disk in _disks_list_from_storage(coordinator):
        entities.extend(
            [
                DiskTemperatureSensor(coordinator, entry, disk),
                DiskCapacityBytesSensor(coordinator, entry, disk),
                DiskRpmSensor(coordinator, entry, disk),
                DiskStateEnumSensor(coordinator, entry, disk),
                DiskPowerOnHoursSensor(coordinator, entry, disk),
                DiskSmartBadSectorsSensor(coordinator, entry, disk),
                DiskSmartUncorrectableSensor(coordinator, entry, disk),
                DiskReadErrorRateSensor(coordinator, entry, disk),
            ]
        )

    async_add_entities(entities)


class BaseUDSensor(CoordinatorEntity[UnifiDriveCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: UnifiDriveCoordinator,
        entry: ConfigEntry,
        name_suffix: str,
        icon: Optional[str] = None,
    ) -> None:
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


class SimpleTextSensor(BaseUDSensor):
    _attr_state_class = None

    def __init__(self, coordinator, entry, path, friendly, icon):
        super().__init__(coordinator, entry, "_".join(path), icon)
        self._path = path
        self._attr_name = friendly

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        cur = data
        for k in self._path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(k)
        return cur


class CpuLoadSensor(BaseUDSensor):
    _attr_name = "CPU Load"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "cpu_load", "mdi:cpu-64-bit")

    @property
    def native_value(self):
        cpu = ((self.coordinator.data or {}).get("device") or {}).get("cpu") or {}
        load = cpu.get("currentload")
        if load is None:
            return None
        return round(load * 100.0, 2) if load <= 1 else round(float(load), 2)


class CpuTempSensor(BaseUDSensor):
    _attr_name = "CPU Temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "cpu_temp", "mdi:thermometer")

    @property
    def native_value(self):
        cpu = ((self.coordinator.data or {}).get("device") or {}).get("cpu") or {}
        t = cpu.get("temperature")
        try:
            return round(float(t), 1) if t is not None else None
        except (TypeError, ValueError):
            return None


class MemBytesSensor(BaseUDSensor):
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.BYTES
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, path, friendly):
        super().__init__(coordinator, entry, "_".join(path), "mdi:memory")
        self._path = path
        self._attr_name = friendly

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        cur = data
        for k in self._path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(k)
            if cur is None:
                return None
        return _kib_to_bytes(cur)


class MemUsagePercentSensor(BaseUDSensor):
    _attr_name = "Memory Usage"
    _attr_icon = "mdi:memory"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "memory_usage_percent", "mdi:memory")

    @property
    def native_value(self):
        mem = ((self.coordinator.data or {}).get("device") or {}).get("memory") or {}
        total = _maybe_int(mem.get("total"))
        avail = _maybe_int(mem.get("available"))
        if avail is None:
            avail = _maybe_int(mem.get("free"))
        if not total or total <= 0 or avail is None:
            return None
        pct = ((total - avail) / total) * 100.0
        return round(max(0.0, min(100.0, pct)), 1)


class MemUsedBytesSensor(BaseUDSensor):
    _attr_name = "Memory Used"
    _attr_icon = "mdi:memory"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.BYTES
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "memory_used_bytes", "mdi:memory")

    @property
    def native_value(self):
        mem = ((self.coordinator.data or {}).get("device") or {}).get("memory") or {}
        total_kib = _maybe_int(mem.get("total"))
        avail_kib = _maybe_int(mem.get("available"))
        if avail_kib is None:
            avail_kib = _maybe_int(mem.get("free"))
        if not total_kib or total_kib <= 0 or avail_kib is None:
            return None
        used_kib = max(0, total_kib - avail_kib)
        return _kib_to_bytes(used_kib)


class ActiveNicSpeedSensor(BaseUDSensor):
    _attr_name = "Active NIC Link Speed"
    _attr_device_class = SensorDeviceClass.DATA_RATE
    _attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
    _attr_icon = "mdi:lan"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "nic_speed", "mdi:lan")

    @staticmethod
    def _parse_speed_mbps(text: str | None) -> Optional[int]:
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

    @property
    def native_value(self):
        dev = (self.coordinator.data or {}).get("device") or {}
        nics = dev.get("networkInterfaces") or []
        nic = None
        for n in nics:
            if n.get("connected"):
                nic = n
                break
        if nic is None and nics:
            nic = nics[0]
        if not nic:
            return None
        return self._parse_speed_mbps(nic.get("linkSpeed"))


class FanProfileSensor(BaseUDSensor):
    _attr_name = "Fan Profile"
    _attr_icon = "mdi:fan"
    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "fan_profile", "mdi:fan")
        self._attr_options = None

    @property
    def native_value(self):
        fan = (self.coordinator.data or {}).get("fan_control") or {}
        aps = fan.get("availableProfiles")
        if isinstance(aps, list):
            self._attr_options = sorted({a for a in aps if isinstance(a, str)})
        return fan.get("currentProfile")


class _StorageTotalsMixin:
    @staticmethod
    def _totals_bytes(root: dict[str, Any]) -> tuple[int, int, int]:
        storage = (root or {}).get("storage") or {}
        pools = storage.get("pools")
        if isinstance(pools, list) and pools:
            try:
                total_b = sum(float(p.get("capacity") or 0) for p in pools)
                used_b = sum(float(p.get("usage") or 0) for p in pools)
                free_b = max(0.0, total_b - used_b)
                return int(total_b), int(used_b), int(free_b)
            except Exception:
                pass

        vols = (root or {}).get("volumes")
        if vols:
            items = vols if isinstance(vols, list) else vols.get("items") if isinstance(vols, dict) else []
            total = used = free = 0.0
            for v in items:
                t = v.get("sizeBytes") or v.get("size") or 0
                u = v.get("usedBytes") or v.get("used") or 0
                f = v.get("availableBytes") or v.get("free") or (t - u if t and u else 0)
                try:
                    total += float(t)
                    used += float(u)
                    free += float(f)
                except Exception:
                    continue
            if total or used or free:
                return int(total), int(used), int(free)

        dev = (root or {}).get("device") or {}
        storage_list = dev.get("storage")
        if isinstance(storage_list, list):
            raid = next((s for s in storage_list if s.get("type") == "raid"), None)
            if raid and all(k in raid for k in ("size", "used", "avail")):
                try:
                    total_b = float(raid["size"])
                    used_b = float(raid["used"])
                    free_b = float(raid["avail"])
                    return int(total_b), int(used_b), int(free_b)
                except Exception:
                    pass

        return 0, 0, 0


class StorageTotalBytesSensor(_StorageTotalsMixin, BaseUDSensor):
    _attr_name = "Storage Total"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.BYTES
    _attr_icon = "mdi:database"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "storage_total_bytes", "mdi:database")

    @property
    def native_value(self):
        t, _, _ = self._totals_bytes(self.coordinator.data or {})
        return t or None


class StorageUsedBytesSensor(_StorageTotalsMixin, BaseUDSensor):
    _attr_name = "Storage Used"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.BYTES
    _attr_icon = "mdi:database"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "storage_used_bytes", "mdi:database")

    @property
    def native_value(self):
        _, u, _ = self._totals_bytes(self.coordinator.data or {})
        return u or None


class StorageFreeBytesSensor(_StorageTotalsMixin, BaseUDSensor):
    _attr_name = "Storage Free"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.BYTES
    _attr_icon = "mdi:database"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "storage_free_bytes", "mdi:database")

    @property
    def native_value(self):
        _, _, f = self._totals_bytes(self.coordinator.data or {})
        return f or None


class StorageUsedPercentSensor(_StorageTotalsMixin, BaseUDSensor):
    _attr_name = "Storage Used Percent"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:database-percent"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "storage_used_percent", "mdi:database-percent")

    @property
    def native_value(self):
        t, u, _ = self._totals_bytes(self.coordinator.data or {})
        if t <= 0:
            return None
        return round((u / t) * 100.0, 1)


class SharesCountSensor(BaseUDSensor):
    _attr_name = "Shares Count"
    _attr_icon = "mdi:folder-multiple"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "shares_count", "mdi:folder-multiple")

    @property
    def native_value(self):
        shares = (self.coordinator.data or {}).get("shares")
        items = shares if isinstance(shares, list) else shares.get("items") if isinstance(shares, dict) else []
        return len(items)


class DisksCountSensor(BaseUDSensor):
    _attr_name = "Disks Count"
    _attr_icon = "mdi:harddisk"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "disks_count", "mdi:harddisk")

    @property
    def native_value(self):
        storage = (self.coordinator.data or {}).get("storage") or {}
        disks = storage.get("disks") or []
        return sum(1 for d in disks if (d.get("state") or "").lower() != "empty")


class HottestDiskTempSensor(BaseUDSensor):
    _attr_name = "Hottest Disk Temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer-water"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "hottest_disk_temp", "mdi:thermometer-water")

    @property
    def native_value(self):
        storage = (self.coordinator.data or {}).get("storage") or {}
        disks = storage.get("disks") or []
        temps = [d.get("temperature") for d in disks if isinstance(d.get("temperature"), (int, float))]
        return max(temps) if temps else None


def _drives_list(coordinator: UnifiDriveCoordinator) -> list[dict[str, Any]]:
    drives = (coordinator.data or {}).get("drives") or {}
    return drives.get("drives") if isinstance(drives, dict) else []


class _BaseDriveEntity(BaseUDSensor):
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


class DriveUsageBytesSensor(_BaseDriveEntity):
    _attr_name = "Usage"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.BYTES
    _attr_icon = "mdi:database"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, drive_id, drive_name):
        super().__init__(coordinator, entry, drive_id, drive_name, "usage_bytes", "mdi:database")

    @property
    def native_value(self):
        d = self._find_drive()
        if not d:
            return None
        try:
            return int(d.get("usage", 0))
        except Exception:
            return None


class DriveStatusEnumSensor(_BaseDriveEntity):
    _attr_name = "Status"
    _attr_icon = "mdi:checkbox-marked-circle-outline"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["active", "inactive", "unknown"]

    def __init__(self, coordinator, entry, drive_id, drive_name):
        super().__init__(coordinator, entry, drive_id, drive_name, "status", "mdi:checkbox-marked-circle-outline")

    @property
    def native_value(self):
        d = self._find_drive()
        v = (d or {}).get("status")
        return v if isinstance(v, str) else None


class DriveMemberCountSensor(_BaseDriveEntity):
    _attr_name = "Member Count"
    _attr_icon = "mdi:account-multiple"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, drive_id, drive_name):
        super().__init__(coordinator, entry, drive_id, drive_name, "member_count", "mdi:account-multiple")

    @property
    def native_value(self):
        d = self._find_drive()
        return (d or {}).get("memberCount")

def _disks_list_from_storage(coordinator) -> list[dict]:
    storage = (coordinator.data or {}).get("storage") or {}
    disks = storage.get("disks") or []
    return [d for d in disks if (d.get("state") or "").lower() != "empty"]


class _BaseDiskEntity(BaseUDSensor):
    def __init__(self, coordinator, entry, disk: dict, suffix: str, icon: str | None = None):
        serial = disk.get("serial") or f"slot{disk.get('slotId','?')}"
        super().__init__(coordinator, entry, f"disk_{serial}_{suffix}", icon)
        self._serial = serial
        self._slot = str(disk.get("slotId") or "?")
        self._model = disk.get("model") or "Disk"
        self._disk_id_key = serial

    @property
    def name(self) -> str | None:
        base = f"Disk {self._slot} ({self._model})"
        return f"{base} {self._attr_name}" if self._attr_name else base

    def _find_disk(self) -> dict | None:
        for d in _disks_list_from_storage(self.coordinator):
            sid = d.get("serial") or f"slot{d.get('slotId')}"
            if sid == self._disk_id_key:
                return d
        return None


class DiskTemperatureSensor(_BaseDiskEntity):
    _attr_name = "Temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, disk):
        super().__init__(coordinator, entry, disk, "temp", "mdi:thermometer")

    @property
    def native_value(self):
        d = self._find_disk()
        t = (d or {}).get("temperature")
        return round(float(t), 1) if isinstance(t, (int, float)) else None


class DiskCapacityBytesSensor(_BaseDiskEntity):
    _attr_name = "Capacity"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.BYTES
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, disk):
        super().__init__(coordinator, entry, disk, "capacity_bytes", "mdi:harddisk")

    @property
    def native_value(self):
        d = self._find_disk()
        sz = (d or {}).get("size")
        try:
            return int(sz) if sz is not None else None
        except Exception:
            return None


class DiskRpmSensor(_BaseDiskEntity):
    _attr_name = "RPM"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, disk):
        super().__init__(coordinator, entry, disk, "rpm", "mdi:rotate-right")

    @property
    def native_value(self):
        d = self._find_disk()
        rpm = (d or {}).get("rpm")
        return int(rpm) if isinstance(rpm, (int, float)) else None


class DiskStateEnumSensor(_BaseDiskEntity):
    _attr_name = "State"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_icon = "mdi:checkbox-marked-circle-outline"

    def __init__(self, coordinator, entry, disk):
        super().__init__(coordinator, entry, disk, "state", "mdi:checkbox-marked-circle-outline")
        self._attr_options = None

    @property
    def native_value(self):
        d = self._find_disk()
        state = ((d or {}).get("state") or "").lower() or None
        opts = set(self._attr_options or [])
        for x in _disks_list_from_storage(self.coordinator):
            s = (x.get("state") or "").lower()
            if s:
                opts.add(s)
        self._attr_options = sorted(opts) if opts else None
        return state


class DiskPowerOnHoursSensor(_BaseDiskEntity):
    _attr_name = "Power On"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, disk):
        super().__init__(coordinator, entry, disk, "power_on_hours", "mdi:clock-outline")

    @property
    def native_value(self):
        d = self._find_disk()
        poh = (d or {}).get("powerOnHours")
        return int(poh) if isinstance(poh, (int, float)) else None


class DiskSmartBadSectorsSensor(_BaseDiskEntity):
    _attr_name = "SMART Bad Sectors"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, disk):
        super().__init__(coordinator, entry, disk, "smart_bad_sectors", "mdi:alert-decagram")

    @property
    def native_value(self):
        d = self._find_disk()
        v = (d or {}).get("badSectorCount")
        return int(v) if isinstance(v, (int, float)) else None


class DiskSmartUncorrectableSensor(_BaseDiskEntity):
    _attr_name = "SMART Uncorrectable"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, disk):
        super().__init__(coordinator, entry, disk, "smart_uncorrectable", "mdi:alert")

    @property
    def native_value(self):
        d = self._find_disk()
        v = (d or {}).get("uncorrectableSectorCount")
        return int(v) if isinstance(v, (int, float)) else None


class DiskReadErrorRateSensor(_BaseDiskEntity):
    _attr_name = "Read Error Rate"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, disk):
        super().__init__(coordinator, entry, disk, "read_error_rate", "mdi:chart-line")

    @property
    def native_value(self):
        d = self._find_disk()
        v = (d or {}).get("readErrorRate") or (d or {}).get("smartReadErrorCount")
        return int(v) if isinstance(v, (int, float)) else None
