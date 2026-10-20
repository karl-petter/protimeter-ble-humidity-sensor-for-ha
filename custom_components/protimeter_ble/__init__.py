"""Protimeter BLE integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import ProtimeterCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Protimeter BLE from a config entry."""
    coordinator = ProtimeterCoordinator(hass, entry)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Kick off the first history fetch in the background so HA startup is not
    # blocked. Sensor entities will show "unavailable" until the fetch completes.
    # Subsequent fetches run on the coordinator's normal schedule (weekly by default),
    # or when the user presses the "Fetch history" button.
    # Tied to the entry via async_create_background_task so a reload/unload
    # while this first fetch is still running cancels it instead of leaving
    # it to race a second connection from the freshly (re)loaded coordinator.
    entry.async_create_background_task(
        hass, coordinator.async_refresh(), name=f"{DOMAIN}_{entry.entry_id}_initial_fetch"
    )

    # Reload the entry when the user changes options (e.g. fetch interval)
    entry.async_on_unload(
        entry.add_update_listener(_async_update_options_listener)
    )

    return True


async def _async_update_options_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload the config entry, but only if entry.options actually changed.

    This listener also fires for entry.data-only writes (the coordinator
    persists CONF_LAST_RECORD_ID after every fetch), which must not reload
    the entry - see ProtimeterCoordinator.should_reload_for_options.
    """
    coordinator: ProtimeterCoordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.should_reload_for_options(entry):
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
