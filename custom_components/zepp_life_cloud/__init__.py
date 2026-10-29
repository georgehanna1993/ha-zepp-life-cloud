"""Unofficial Zepp Life cloud integration."""
from __future__ import annotations
import asyncio
import logging
from datetime import timedelta
import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from .api import ZeppClient, AuthError, CloudError
from .const import DOMAIN, DEFAULT_INTERVAL

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.BUTTON]

class ZeppCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(minutes=entry.options.get("interval", DEFAULT_INTERVAL)))
        self.entry = entry
        self.client = ZeppClient(async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar()), entry.data)

    async def _async_update_data(self):
        try:
            async with asyncio.timeout(60):
                latest = await self.client.latest()
            credentials = self.client.export_credentials()
            if credentials != dict(self.entry.data):
                self.hass.config_entries.async_update_entry(self.entry, data=credentials)
            return {"latest": latest, "last_sync": dt_util.utcnow()}
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from None
        except CloudError as err:
            raise UpdateFailed(str(err)) from None
        except (aiohttp.ClientError, TimeoutError):
            raise UpdateFailed("Unable to reach Zepp/Xiaomi cloud. Check network access.") from None

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = ZeppCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True

async def _options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
        return True
    return False
