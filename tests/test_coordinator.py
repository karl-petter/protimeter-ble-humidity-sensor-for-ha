"""
Tests for ProtimeterCoordinator's BLE fetch/cleanup error handling.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakError
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.protimeter_ble.const import CONF_ADDRESS, DOMAIN
from custom_components.protimeter_ble.coordinator import ProtimeterCoordinator

ADDRESS = "AA:BB:CC:DD:EE:FF"


def _make_coordinator(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: ADDRESS}, options={})
    entry.add_to_hass(hass)
    return ProtimeterCoordinator(hass, entry)


async def test_disconnect_error_does_not_mask_the_real_fetch_failure(hass):
    """
    A BLE read failure must surface as UpdateFailed even when the cleanup
    disconnect() call itself also raises - cleanup errors must never replace
    the error that caused the fetch to fail in the first place.
    """
    coordinator = _make_coordinator(hass)
    fake_client = MagicMock()
    fake_client.disconnect = AsyncMock(side_effect=BleakError("already disconnected"))

    with (
        patch(
            "custom_components.protimeter_ble.coordinator.async_ble_device_from_address",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.protimeter_ble.coordinator.establish_connection",
            new=AsyncMock(return_value=fake_client),
        ),
        patch.object(
            coordinator,
            "_discover_command_char",
            side_effect=BleakError("could not read GATT services"),
        ),
    ):
        with pytest.raises(UpdateFailed):
            await coordinator._do_fetch()
