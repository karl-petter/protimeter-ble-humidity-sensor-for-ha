"""Sensor platform for Protimeter BLE."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProtimeterCoordinator
from .parser import ProtimeterRecord


@dataclass(frozen=True, kw_only=True)
class ProtimeterSensorDescription(SensorEntityDescription):
    """Sensor description with a value accessor for ProtimeterRecord."""
    value_fn: Callable[[ProtimeterRecord], float | int]


SENSOR_DESCRIPTIONS: tuple[ProtimeterSensorDescription, ...] = (
    ProtimeterSensorDescription(
        key="humidity",
        name="Humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda r: r.humidity,
    ),
    ProtimeterSensorDescription(
        key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda r: r.temperature,
    ),
    ProtimeterSensorDescription(
        key="battery",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda r: r.battery,
    ),
    ProtimeterSensorDescription(
        key="wme",
        name="Wood Moisture Equivalent",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:tree",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda r: r.wme,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from a config entry."""
    coordinator: ProtimeterCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ProtimeterSensor(coordinator, entry, desc)
        for desc in SENSOR_DESCRIPTIONS
    )


class ProtimeterSensor(
    CoordinatorEntity[ProtimeterCoordinator], SensorEntity
):
    """A single Protimeter measurement sensor.

    Shows the value from the most-recent historical record.
    Detailed history is stored as HA long-term statistics
    (statistic_id: protimeter_ble:<addr>_<key>).
    """

    entity_description: ProtimeterSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ProtimeterCoordinator,
        entry: ConfigEntry,
        description: ProtimeterSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=entry.data.get(CONF_NAME, coordinator.address),
            manufacturer="Protimeter",
            model="BLE Humidity Sensor",
        )

    @property
    def native_value(self) -> float | int | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
