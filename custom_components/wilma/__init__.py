"""
__init__.py — Integration entry point (config-flow based)
==========================================================
PURPOSE
    Sets up the Wilma integration from a config entry created by the UI
    flow in config_flow.py. No YAML configuration is used.

HOW IT WORKS
    async_setup_entry(hass, entry)
        Called by HA when a config entry is loaded (on startup or after
        the user adds the integration). Creates the coordinator, does the
        first data fetch, and forwards setup to the sensor platform.

    async_unload_entry(hass, entry)
        Called when the user removes the integration or HA is shutting
        down. Unloads all platforms and cleans up hass.data.

    async_reload_entry(hass, entry)
        Called when the user changes options (e.g. poll interval). Unloads
        and re-loads the entry so the new scan_interval takes effect.

    hass.data[DOMAIN][entry.entry_id]
        Each config entry gets its own coordinator stored here. Using
        entry.entry_id as the key supports multiple Wilma accounts.

    scan_interval precedence
        entry.options takes precedence over entry.data so that options-
        flow changes override the value set at creation time.
"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    CONF_BASE_URL,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_CHILDREN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)
from .coordinator import WilmaCoordinator

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    coordinator = WilmaCoordinator(
        hass,
        base_url=entry.data[CONF_BASE_URL],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        children=entry.data[CONF_CHILDREN],
        scan_interval=scan_interval,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
