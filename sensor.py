from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    UnitOfTemperature,
    UnitOfDataRate,
    UnitOfInformation,
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: UnifiDriveCoordinator = data["coordinator"]

    entities: list[SensorEntity] = []

    # System sensors
    entities.extend([
        SimpleTextSensor(coordinator, entry, ("device", "firmwareVersion"), "Firmware Version", "mdi:nas"),
        SimpleTextSensor(coordinator, entry, ("device", "version"), "Drive App Version", "mdi:information-outline"),
        SimpleTextSensor(coordinator, entry, ("device", "status"), "System Status", "mdi:checkbox-marked-circle-outline"),
        CpuLoadSensor(coordinator, entry),
        CpuTempSensor(coordinator, entry),
        MemBytesSensor(coordinator, entry, ("device", "memory", "total"), "Memory Total"),
        MemBytesSensor(coordinator, entry, ("device", "memory", "available"), "Memory Available"),
        MemBytesSensor(coordinator, entry, ("device", "memory", "free"), "Memory Free"),
        MemUsagePercentSensor(coordinator, entry),
        ActiveNicSpeedSensor(coordinator, entry),
        FanProfileSensor(coordinator, entry),
    ])

    # Storage
    entities.extend([
        StorageTotalBytesSensor(coordinator, entry),
        StorageUsedBytesSensor(coordinator, entry),
        StorageFreeBytesSensor(coordinator, entry),
        StorageUsedPercentSensor(coordinator, entry),
        SharesCountSensor(coordinator, entry),
        DisksCountSensor(coordinator, entry),
        HottestDiskTempSensor(coordinator, entry),
    ])

    # Drives
    drives = (coordinator.data or {}).get("drives") or {}
    drive_items = drives.get("drives") if isinstance(drives, dict) else []
    for d in drive_items or []:
        did = d.get("id")
        name = d.get("name") or did or "Drive"
        if not did:
            continue
        entities.extend([
            DriveUsageBytesSensor(coordinator, entry, did, name),
            DriveStatusEnumSensor(coordinator, entry, did, name),
            DriveMemberCountSensor(coordinator, entry, did, name),
        ])

    async_add_entities(entities)


class BaseUDSensor(CoordinatorEntity[UnifiDriveCoordinator], SensorEntity):
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
        free = _maybe_int(mem.get("free"))
        if not total or total <= 0 or free is None:
            return None
        return round(((total - free) / total) * 100.0, 1)


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
        """
        Return (total_bytes, used_bytes, free_bytes).
        Prefer the /storage payload (pools[capacity/usage]), with a robust fallback.
        """
        # Primary: /proxy/drive/api/v2/storage
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

        # Fallback 1: volumes array (if your device exposes it)
        vols = (root or {}).get("volumes")
        if vols:
            items = vols if isinstance(vols, list) else vols.get("items") if isinstance(vols, dict) else []
            total = used = free = 0.0
            for v in items:
                t = v.get("sizeBytes") or v.get("size") or 0
                u = v.get("usedBytes") or v.get("used") or 0
                f = v.get("availableBytes") or v.get("free") or (t - u if t and u else 0)
                try:
                    total += float(t); used += float(u); free += float(f)
                except Exception:
                    continue
            if total or used or free:
                return int(total), int(used), int(free)

        # Fallback 2: websocket-style snapshot under device.storage (if ever present)
        dev = (root or {}).get("device") or {}
        storage_list = dev.get("storage")
        if isinstance(storage_list, list):
            # Look for the main RAID mount (/srv) block if available
            raid = next((s for s in storage_list if s.get("type") == "raid"), None)
            if raid and all(k in raid for k in ("size", "used", "avail")):
                try:
                    total_b = float(raid["size"])
                    used_b = float(raid["used"])
                    free_b = float(raid["avail"])
                    return int(total_b), int(used_b), int(free_b)
                except Exception:
                    pass

        # Nothing usable
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


# Drives (per-drive)
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
