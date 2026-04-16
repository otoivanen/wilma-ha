"""
__init__.py — Integration entry point
======================================
PURPOSE
    This is the first file HA loads when it sees "wilma:" in
    configuration.yaml. It is responsible for three things:
      1. Declaring the shape of the YAML config block (CONFIG_SCHEMA)
      2. Creating the coordinator and doing the first data fetch
      3. Telling HA to also load the sensor platform

HOW IT WORKS (HA concepts)
    CONFIG_SCHEMA
        A voluptuous schema that HA validates configuration.yaml against
        before async_setup is ever called. If you typo a key or pass the
        wrong type you get a clear error at startup rather than a crash
        deep in your code. vol.ALLOW_EXTRA is set so HA's own top-level
        keys (like homeassistant:, logger:, etc.) are not rejected.

    async_setup(hass, config)
        HA calls this once at startup after the schema passes. The full
        parsed configuration.yaml is in `config`; our block is at
        config[DOMAIN]. Returning True tells HA the integration loaded
        successfully. Returning False (or raising) marks it as failed.

    hass.data[DOMAIN]
        A global dict HA provides for integrations to share objects
        between files. We store the coordinator here so sensor.py can
        retrieve it without passing it explicitly. Think of it as the
        integration's own namespace inside HA's runtime.

    async_load_platform()
        Tells HA to load the "sensor" platform belonging to this
        integration. HA will import sensor.py and call
        async_setup_platform() inside it. We wrap it in
        async_create_task() so it runs after async_setup returns —
        the coordinator must be stored in hass.data first.

    scan_interval
        How often HA polls Wilma, in seconds. Configured in
        configuration.yaml (default: 14400 = 4 hours). The coordinator
        manages the timer automatically via update_interval.

NOTE: This YAML-based setup will be replaced by a UI config flow in the
next phase. The base_url, username, password, scan_interval, and children
will then be configured through Settings → Devices & Services instead.
"""

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform

from .coordinator import WilmaCoordinator

DOMAIN = "wilma"

CONF_BASE_URL = "base_url"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_CHILDREN = "children"
CONF_CHILD_NAME = "name"
CONF_CHILD_ID = "id"

CHILD_SCHEMA = vol.Schema({
    vol.Required(CONF_CHILD_NAME): cv.string,
    vol.Required(CONF_CHILD_ID): cv.string,
})

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_BASE_URL): cv.url,
                vol.Required(CONF_USERNAME): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
                vol.Optional(CONF_SCAN_INTERVAL, default=14400): cv.positive_int,
                vol.Required(CONF_CHILDREN): [CHILD_SCHEMA],
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    domain_config = config[DOMAIN]

    coordinator = WilmaCoordinator(
        hass,
        base_url=domain_config[CONF_BASE_URL],
        username=domain_config[CONF_USERNAME],
        password=domain_config[CONF_PASSWORD],
        children=domain_config[CONF_CHILDREN],
        scan_interval=domain_config[CONF_SCAN_INTERVAL],
    )

    # Initial fetch so sensors have data immediately on startup
    await coordinator.async_refresh()

    hass.data[DOMAIN] = coordinator

    hass.async_create_task(
        async_load_platform(hass, "sensor", DOMAIN, {}, config)
    )

    return True
