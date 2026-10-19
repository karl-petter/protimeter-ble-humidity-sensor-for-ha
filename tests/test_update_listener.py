"""
Tests for the config-entry update listener in __init__.py.

The coordinator persists CONF_LAST_RECORD_ID into entry.data after every
successful fetch (see coordinator.py's _do_fetch). That write must not
trigger a reload - only an actual change to entry.options (the fetch
interval, set via the options flow) should. These tests exercise the
listener in isolation with a fake coordinator, so they don't depend on
instantiating the real ProtimeterCoordinator (which needs a full Home
Assistant runtime).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.protimeter_ble import DOMAIN, _async_update_options_listener


class _FakeEntry:
    def __init__(self, entry_id: str = "entry1") -> None:
        self.entry_id = entry_id


class _FakeCoordinator:
    """Stands in for ProtimeterCoordinator; only the guard method matters here."""

    def __init__(self, *, options_changed: bool) -> None:
        self._options_changed = options_changed
        self.should_reload_for_options_calls: list[_FakeEntry] = []

    def should_reload_for_options(self, entry: _FakeEntry) -> bool:
        self.should_reload_for_options_calls.append(entry)
        return self._options_changed


def _hass_with_coordinator(entry: _FakeEntry, coordinator: _FakeCoordinator) -> MagicMock:
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator}}
    hass.config_entries.async_reload = AsyncMock()
    return hass


@pytest.mark.asyncio
async def test_listener_skips_reload_when_only_data_changed():
    """A data-only update (e.g. CONF_LAST_RECORD_ID) must not reload the entry."""
    entry = _FakeEntry()
    coordinator = _FakeCoordinator(options_changed=False)
    hass = _hass_with_coordinator(entry, coordinator)

    await _async_update_options_listener(hass, entry)

    hass.config_entries.async_reload.assert_not_called()
    assert coordinator.should_reload_for_options_calls == [entry]


@pytest.mark.asyncio
async def test_listener_reloads_when_options_changed():
    """A real options-flow change (e.g. fetch interval) must still reload."""
    entry = _FakeEntry()
    coordinator = _FakeCoordinator(options_changed=True)
    hass = _hass_with_coordinator(entry, coordinator)

    await _async_update_options_listener(hass, entry)

    hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)
