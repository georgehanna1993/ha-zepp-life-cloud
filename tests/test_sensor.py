"""Sensor behavior tests with small HA interface stubs, not a full HA runtime."""
import importlib.util
import math
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/zepp_life_cloud"
class CoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator
class SensorEntity:
    pass
class DeviceInfo(dict):
    pass
mods = {
    "homeassistant": {},
    "homeassistant.components": {},
    "homeassistant.components.sensor": {"SensorEntity": SensorEntity, "SensorDeviceClass": types.SimpleNamespace(TIMESTAMP="timestamp", WEIGHT="weight"), "SensorStateClass": types.SimpleNamespace(MEASUREMENT="measurement")},
    "homeassistant.core": {"callback": lambda f:f},
    "homeassistant.helpers": {},
    "homeassistant.helpers.entity": {"DeviceInfo": DeviceInfo},
    "homeassistant.helpers.update_coordinator": {"CoordinatorEntity": CoordinatorEntity},
}
# These tests intentionally do not import HA's integration __init__.
for name, attrs in mods.items():
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
package = types.ModuleType("test_zlc")
package.__path__ = [str(ROOT)]
sys.modules["test_zlc"] = package
def load(name):
    spec = importlib.util.spec_from_file_location("test_zlc." + name, ROOT / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m
const = load("const")
sensor = load("sensor")

class SensorTests(unittest.TestCase):
    def setUp(self):
        self.entry=types.SimpleNamespace(unique_id="123:-1",title="Example")
        self.coordinator=types.SimpleNamespace(entry=self.entry,data={"latest":{"generatedTime":100,"summary":{"weight":86.5,"fatRate":20,"bodyStyle":0}},"last_sync":"now"})
    def entity(self,key,raw=False):
        return sensor.ZeppSensor(self.coordinator,key,key,None,raw=raw)
    def test_sensor_icons_and_seconds_metric_removed(self):
        self.assertEqual(self.entity("weight")._attr_icon, "mdi:scale-bathroom")
        self.assertEqual(self.entity("fatRate")._attr_icon, "mdi:percent")
        self.assertEqual(self.entity("last_sync")._attr_icon, "mdi:cloud-sync-outline")
        self.assertNotIn("oneFootMeasureTime", [key for key, _, _ in const.METRICS])

    def test_cloud_value_direct(self):
        self.assertEqual(self.entity("fatRate").native_value,20)
    def test_missing_metric_is_unknown(self):
        self.assertIsNone(self.entity("boneMass").native_value)
    def test_zero_placeholder_is_unknown(self):
        self.coordinator.data["latest"]["summary"]["fatRate"]=0
        self.assertIsNone(self.entity("fatRate").native_value)
    def test_categorical_zero_and_raw_zero_retained(self):
        self.assertEqual(self.entity("bodyStyle").native_value,0)
        self.coordinator.data["latest"]["summary"]["custom"]=0
        self.assertEqual(self.entity("custom",raw=True).native_value,0)
    def test_bad_number_is_unknown(self):
        for value in ("bad",float("nan"),float("inf"),True,-1):
            self.coordinator.data["latest"]["summary"]["fatRate"]=value
            self.assertIsNone(self.entity("fatRate").native_value)
    def test_no_measurement_is_unknown(self):
        self.coordinator.data["latest"]=None
        self.assertIsNone(self.entity("weight").native_value)
    def test_weight_attributes_only_numeric(self):
        self.coordinator.data["latest"]["summary"]["secret"]="not returned"
        self.coordinator.data["latest"]["summary"]["bad"]=float("nan")
        attrs=self.entity("weight").extra_state_attributes["cloud_summary"]
        self.assertNotIn("secret",attrs)
        self.assertNotIn("bad",attrs)
    def test_timestamp(self):
        self.assertEqual(self.entity("last_weigh_in").native_value.timestamp(),100)

class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_numeric_sensor_added_on_initial_and_later_updates(self):
        added=[]
        listeners=[]
        entry=types.SimpleNamespace(entry_id="entry",unique_id="123:-1",title="Example",async_on_unload=lambda _:None)
        coordinator=types.SimpleNamespace(entry=entry,data={"latest":{"generatedTime":100,"summary":{"weight":86.5,"extraMetric":7,"source":1}}})
        coordinator.async_add_listener=lambda f: listeners.append(f)
        hass=types.SimpleNamespace(data={const.DOMAIN:{"entry":coordinator}})
        await sensor.async_setup_entry(hass,entry,lambda entities:added.extend(entities))
        self.assertEqual(len([e for e in added if e.key=="extraMetric"]),1)
        self.assertFalse(any(e.key=="source" for e in added))
        coordinator.data["latest"]["summary"]["laterMetric"]=8
        listeners[0]()
        listeners[0]()
        self.assertEqual(len([e for e in added if e.key=="laterMetric"]),1)

if __name__ == "__main__":
    unittest.main()
