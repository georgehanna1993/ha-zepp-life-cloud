"""Manual sync uses the same coordinator as scheduled polling."""
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ZeppSyncButton(hass.data[DOMAIN][entry.entry_id])])

class ZeppSyncButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Sync now"
    _attr_icon = "mdi:cloud-sync"
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.entry.unique_id + "_sync"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.entry.unique_id)})
    async def async_press(self):
        await self.coordinator.async_request_refresh()
