"""Config flow for Protimeter BLE integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback

from .const import (
    ADVERTISED_SERVICE_UUID,
    CONF_ADDRESS,
    CONF_FETCH_INTERVAL_DAYS,
    DEFAULT_FETCH_INTERVAL_DAYS,
    DEFAULT_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Choices shown in the fetch-interval selector (values are days)
FETCH_INTERVAL_OPTIONS = {
    1:  "Every day",
    3:  "Every 3 days",
    7:  "Every week",
    14: "Every 2 weeks",
    30: "Every month",
}


def _fetch_interval_schema(default: int) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_FETCH_INTERVAL_DAYS, default=default): vol.In(
                FETCH_INTERVAL_OPTIONS
            ),
        }
    )


class ProtimeterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Protimeter BLE."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}   # {address: name}

    # ── Bluetooth discovery (automatic) ───────────────────────────────────────

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a device discovered via the HA Bluetooth integration."""
        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or DEFAULT_NAME,
            "address": discovery_info.address,
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding the discovered device."""
        assert self._discovery_info is not None
        info = self._discovery_info

        if user_input is not None:
            return self._create_entry(
                address=info.address.upper(),
                name=user_input.get(CONF_NAME) or info.name or DEFAULT_NAME,
                fetch_interval_days=user_input.get(
                    CONF_FETCH_INTERVAL_DAYS, DEFAULT_FETCH_INTERVAL_DAYS
                ),
            )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": info.name or DEFAULT_NAME,
                "address": info.address,
            },
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_NAME, default=info.name or DEFAULT_NAME
                    ): str,
                    vol.Required(
                        CONF_FETCH_INTERVAL_DAYS,
                        default=DEFAULT_FETCH_INTERVAL_DAYS,
                    ): vol.In(FETCH_INTERVAL_OPTIONS),
                }
            ),
        )

    # ── Manual setup (user-initiated) ─────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show discovered devices, or fall back to manual entry if none found."""
        self._discovered_devices = {
            info.address.upper(): info.name or info.address
            for info in async_discovered_service_info(self.hass, connectable=True)
            if ADVERTISED_SERVICE_UUID.lower()
            in [s.lower() for s in info.service_uuids]
            or (info.name or "").startswith("Protimeter_")
        }

        if self._discovered_devices:
            return await self.async_step_pick_device()
        return await self.async_step_manual()

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick from discovered devices."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            return self._create_entry(
                address=address,
                name=self._discovered_devices[address],
                fetch_interval_days=user_input.get(
                    CONF_FETCH_INTERVAL_DAYS, DEFAULT_FETCH_INTERVAL_DAYS
                ),
            )

        return self.async_show_form(
            step_id="pick_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices),
                    vol.Required(
                        CONF_FETCH_INTERVAL_DAYS,
                        default=DEFAULT_FETCH_INTERVAL_DAYS,
                    ): vol.In(FETCH_INTERVAL_OPTIONS),
                }
            ),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual MAC address entry fallback."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].upper().strip()
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            return self._create_entry(
                address=address,
                name=user_input.get(CONF_NAME) or DEFAULT_NAME,
                fetch_interval_days=user_input.get(
                    CONF_FETCH_INTERVAL_DAYS, DEFAULT_FETCH_INTERVAL_DAYS
                ),
            )

        return self.async_show_form(
            step_id="manual",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Required(
                        CONF_FETCH_INTERVAL_DAYS,
                        default=DEFAULT_FETCH_INTERVAL_DAYS,
                    ): vol.In(FETCH_INTERVAL_OPTIONS),
                }
            ),
        )

    # ── Options flow ──────────────────────────────────────────────────────────

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ProtimeterOptionsFlow(config_entry)

    # ── Helper ────────────────────────────────────────────────────────────────

    def _create_entry(
        self, address: str, name: str, fetch_interval_days: int
    ) -> ConfigFlowResult:
        return self.async_create_entry(
            title=name,
            data={
                CONF_ADDRESS: address,
                CONF_NAME: name,
                CONF_FETCH_INTERVAL_DAYS: fetch_interval_days,
            },
        )


class ProtimeterOptionsFlow(OptionsFlow):
    """Allow changing the fetch interval after setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._entry.options.get(
            CONF_FETCH_INTERVAL_DAYS,
            self._entry.data.get(CONF_FETCH_INTERVAL_DAYS, DEFAULT_FETCH_INTERVAL_DAYS),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_FETCH_INTERVAL_DAYS, default=current
                    ): vol.In(FETCH_INTERVAL_OPTIONS),
                }
            ),
        )
