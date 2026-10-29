"""Cloud values are exposed as supplied; no body-composition formulas."""
from __future__ import annotations
import math
import re
from homeassistant.core import callback
from datetime import datetime, timezone
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, METRICS

SENSOR_ICONS = {
    "weight": "mdi:scale-bathroom",
    "bmi": "mdi:calculator-variant",
    "fatRate": "mdi:percent",
    "bodyWaterRate": "mdi:water-percent",
    "muscleRate": "mdi:arm-flex",
    "boneMass": "mdi:bone",
    "proteinRatio": "mdi:food-steak",
    "visceralFat": "mdi:heart-pulse",
    "metabolism": "mdi:fire",
    "muscleAge": "mdi:calendar-account",
    "bodyScore": "mdi:star-circle",
    "bodyStyle": "mdi:account",
    "standBodyWeight": "mdi:scale",
    "impedance": "mdi:lightning-bolt",
    "height": "mdi:human-male-height",
    "bodyBalanceScore": "mdi:scale-balance",
    "last_weigh_in": "mdi:clock-check-outline",
    "last_sync": "mdi:cloud-sync-outline",
}

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [ZeppSensor(coordinator, key, name, unit) for key, name, unit in METRICS]
    entities += [ZeppSensor(coordinator, "last_weigh_in", "Timing · Last measurement", None),
                 ZeppSensor(coordinator, "last_sync", "Sync · Last successful sync", None)]
    async_add_entities(entities)
    known = {key for key, _, _ in METRICS}
    known.update(("last_weigh_in", "last_sync"))
    metadata = {"source", "deviceType", "syncHealth", "encryptImpedance"}
    @callback
    def discover_extra_metrics():
        latest = (coordinator.data or {}).get("latest")
        if not latest:
            return
        extra = []
        for key, value in latest["summary"].items():
            if key in known or key in metadata or not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                continue
            known.add(key)
            label = re.sub(r"(?<!^)(?=[A-Z])", " ", key).capitalize()
            extra.append(ZeppSensor(coordinator, key, label + " (cloud)", None, raw=True))
        if extra:
            async_add_entities(extra)
    discover_extra_metrics()
    entry.async_on_unload(coordinator.async_add_listener(discover_extra_metrics))

class ZeppSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, key, name, unit, raw=False):
        super().__init__(coordinator)
        self.key = key
        self.raw = raw
        self._attr_name = name
        self._attr_icon = SENSOR_ICONS.get(key, "mdi:chart-box-outline")
        self._attr_unique_id = coordinator.entry.unique_id + "_" + key
        self._attr_native_unit_of_measurement = unit
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.unique_id)},
            name=coordinator.entry.title + " scale", manufacturer="Xiaomi / Zepp Life")
        if key in ("last_sync", "last_weigh_in"):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        else:
            if key != "bodyStyle":
                self._attr_state_class = SensorStateClass.MEASUREMENT
            if key in ("weight", "muscleRate", "boneMass", "standBodyWeight"):
                self._attr_device_class = SensorDeviceClass.WEIGHT

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        if self.key == "last_sync":
            return data.get("last_sync")
        latest = data.get("latest")
        if not latest:
            return None
        if self.key == "last_weigh_in":
            try:
                return datetime.fromtimestamp(latest["generatedTime"], timezone.utc)
            except (ValueError, OverflowError, OSError):
                return None
        value = latest["summary"].get(self.key)
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        # Zepp often stores unavailable composition fields as zero.
        if not math.isfinite(number) or number < 0 or (number == 0 and self.key != "bodyStyle" and not self.raw):
            return None
        return number

    @property
    def extra_state_attributes(self):
        if self.key != "weight":
            return None
        latest = (self.coordinator.data or {}).get("latest")
        if not latest:
            return None
        # Numeric summary fields include unmapped future metrics, without account data.
        summary = {key: value for key, value in latest["summary"].items()
                   if isinstance(value, (float, int)) and not isinstance(value, bool)
                   and math.isfinite(value)}
        return {"cloud_summary": summary}
