"""Diagnostics deliberately omit credentials, cloud bodies and health values."""
from .const import DOMAIN
async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    return {
        "version": "0.1.0",
        "method": entry.data.get("method"),
        "poll_minutes": entry.options.get("interval", 60),
        "last_update_success": coordinator.last_update_success if coordinator else False,
        "has_measurement": bool(coordinator and coordinator.data and coordinator.data.get("latest")),
        "available_summary_fields": sorted(coordinator.data["latest"]["summary"])
            if coordinator and coordinator.data and coordinator.data.get("latest") else [],
    }
