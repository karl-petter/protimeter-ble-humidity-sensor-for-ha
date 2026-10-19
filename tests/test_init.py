"""
Integration tests for config-entry setup, unload, and the options-update
listener, exercised against a real (test-mode) Home Assistant core.

These complement tests/test_update_listener.py (which pins the listener's
control flow against a fake coordinator) by proving the real HA update-
listener dispatch - hass.config_entries.async_update_entry() - behaves the
way that test assumes: it fires on *any* entry change, data or options, and
our listener must tell those apart via ProtimeterCoordinator.should_reload_for_options.

Entries are set up via hass.config_entries.async_setup() rather than calling
async_setup_entry() directly, since that is what populates DataUpdateCoordinator's
config_entry context (needed for its own unload-triggered shutdown) in real HA.
"""

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.protimeter_ble.const import (
    CONF_ADDRESS,
    CONF_FETCH_INTERVAL_DAYS,
    CONF_LAST_RECORD_ID,
    DOMAIN,
)

ADDRESS = "AA:BB:CC:DD:EE:FF"


def _make_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: ADDRESS, CONF_FETCH_INTERVAL_DAYS: 7},
        options={},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture(autouse=True)
def _skip_real_fetch():
    """These tests cover entry lifecycle, not the BLE fetch kicked off on setup."""
    with patch(
        "custom_components.protimeter_ble.coordinator.ProtimeterCoordinator.async_refresh",
        new=AsyncMock(),
    ):
        yield


async def test_setup_and_unload_entry(hass, enable_bluetooth):
    entry = _make_entry(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.entry_id in hass.data[DOMAIN]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.entry_id not in hass.data[DOMAIN]


async def test_per_fetch_data_write_does_not_reload(hass, enable_bluetooth):
    """Regression test: persisting CONF_LAST_RECORD_ID must not reload the entry."""
    entry = _make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload", new=AsyncMock()
    ) as mock_reload:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_LAST_RECORD_ID: 42}
        )
        await hass.async_block_till_done()
        mock_reload.assert_not_called()

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_options_change_reloads_entry(hass, enable_bluetooth):
    entry = _make_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    with patch(
        "homeassistant.config_entries.ConfigEntries.async_reload", new=AsyncMock()
    ) as mock_reload:
        hass.config_entries.async_update_entry(
            entry, options={CONF_FETCH_INTERVAL_DAYS: 14}
        )
        await hass.async_block_till_done()
        mock_reload.assert_awaited_once_with(entry.entry_id)

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
