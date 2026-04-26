"""Sensor platform for Protimeter BLE."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
import homeassistant.util.dt as dt_util

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
        translation_key="humidity",
        name="Humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda r: r.humidity,
    ),
    ProtimeterSensorDescription(
        key="temperature",
        translation_key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda r: r.temperature,
    ),
    ProtimeterSensorDescription(
        key="battery",
        translation_key="battery",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda r: r.battery,
    ),
    ProtimeterSensorDescription(
        key="wme",
        translation_key="wme",
        name="Wood Moisture Equivalent",
        native_unit_of_measurement=PERCENTAGE,
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
    entities: list[SensorEntity] = [
        ProtimeterSensor(coordinator, entry, desc)
        for desc in SENSOR_DESCRIPTIONS
    ]
    entities.append(ProtimeterTimestampSensor(coordinator, entry))
    async_add_entities(entities)


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
    def available(self) -> bool:
        # Stay available as long as we have data — a failed fetch doesn't
        # invalidate historical values that are already stored locally.
        return self.coordinator.data is not None

    @property
    def native_value(self) -> float | int | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class ProtimeterTimestampSensor(
    CoordinatorEntity[ProtimeterCoordinator], SensorEntity
):
    """Sensor showing when the most-recent record was recorded on the device."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_reading"
    _attr_name = "Last reading"

    def __init__(
        self,
        coordinator: ProtimeterCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_last_reading"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=entry.data.get(CONF_NAME, coordinator.address),
            manufacturer="Protimeter",
            model="BLE Humidity Sensor",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None

    @property
    def native_value(self) -> datetime | None:
        rec = self.coordinator.data
        if rec is None:
            return None
        try:
            naive_local = datetime(
                rec.year, rec.month, rec.day,
                rec.hour, rec.minute, rec.second,
            )
            return naive_local.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        except (ValueError, OverflowError):
            return None
