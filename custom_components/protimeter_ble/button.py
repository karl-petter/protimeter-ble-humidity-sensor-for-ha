"""Button platform for Protimeter BLE — manual history fetch trigger."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProtimeterCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities from a config entry."""
    coordinator: ProtimeterCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ProtimeterFetchButton(coordinator, entry)])


class ProtimeterFetchButton(CoordinatorEntity[ProtimeterCoordinator], ButtonEntity):
    """Button that triggers an immediate history fetch from the device."""

    _attr_has_entity_name = True
    _attr_name = "Fetch history"
    _attr_icon = "mdi:download"

    def __init__(
        self,
        coordinator: ProtimeterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_fetch_history"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=entry.data.get(CONF_NAME, coordinator.address),
            manufacturer="Protimeter",
            model="BLE Humidity Sensor",
        )

    async def async_press(self) -> None:
        """Trigger an immediate history fetch."""
        await self.coordinator.async_refresh()
