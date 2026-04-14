"""Protimeter BLE integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_ADDRESS, DOMAIN
from .coordinator import ProtimeterCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Protimeter BLE from a config entry."""
    coordinator = ProtimeterCoordinator(hass, entry)

    # Fetch history immediately on setup.
    # On the very first add this reads the full history; on HA restarts /
    # option reloads it only reads records since the last saved record_id.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload the entry when the user changes options (e.g. fetch interval)
    entry.async_on_unload(
        entry.add_update_listener(_async_update_options_listener)
    )

    return True


async def _async_update_options_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload the config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
