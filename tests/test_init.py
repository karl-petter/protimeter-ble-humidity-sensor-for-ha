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

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.protimeter_ble.const import (
    CONF_ADDRESS,
    CONF_FETCH_INTERVAL_DAYS,
    CONF_LAST_RECORD_ID,
    DOMAIN,
)
from custom_components.protimeter_ble.coordinator import ProtimeterCoordinator

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


async def test_unload_cancels_in_flight_initial_fetch(hass, enable_bluetooth):
    """
    async_setup_entry kicks off the first history fetch in the background so
    HA startup isn't blocked on a slow BLE read. If the entry is unloaded
    while that fetch is still running, the task must be cancelled - not left
    to keep running against a torn-down config entry.
    """
    entry = _make_entry(hass)
    fetch_started = asyncio.Event()
    task_holder: dict[str, asyncio.Task] = {}

    async def _hang_refresh(self) -> None:
        task_holder["task"] = asyncio.current_task()
        fetch_started.set()
        await asyncio.sleep(100)

    try:
        with patch.object(ProtimeterCoordinator, "async_refresh", new=_hang_refresh):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await asyncio.wait_for(fetch_started.wait(), timeout=5)

            assert await hass.config_entries.async_unload(entry.entry_id)

            # Cancellation is requested synchronously by unload, but only takes
            # effect once the event loop gives the task a turn to raise
            # CancelledError out of its current await point. Bounded instead of
            # hass.async_block_till_done(), which would hang forever here if
            # the task is not actually tied to the entry's lifecycle.
            task = task_holder["task"]
            for _ in range(20):
                if task.cancelled():
                    break
                await asyncio.sleep(0.05)

        assert task.cancelled()
    finally:
        # Guarantee cleanup even if the assertion above fails, so a leftover
        # un-cancelled task (the bug this test targets) can't hang fixture
        # teardown's own wait for all of hass's tracked tasks to finish.
        task = task_holder.get("task")
        if task is not None and not task.done():
            task.cancel()
