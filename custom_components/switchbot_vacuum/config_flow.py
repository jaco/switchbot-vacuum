"""Config flow for SwitchBot Vacuum."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_DEVICE_MAC, CONF_PASSWORD, CONF_USERNAME, DOMAIN, DEVICE_TYPE_S10
from .coordinator import SwitchBotS10Coordinator

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class SwitchBotS10ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SwitchBot Vacuum."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self._username: str = ""
        self._password: str = ""
        self._devices: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step (credentials)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]

            try:
                coordinator = SwitchBotS10Coordinator(self.hass, None)
                coordinator.entry = type("Entry", (), {"data": user_input})()
                await coordinator.async_login()
                self._devices = await coordinator.async_discover_devices()
            except Exception:
                _LOGGER.exception("Authentication failed")
                errors["base"] = "invalid_auth"
            else:
                if not self._devices:
                    errors["base"] = "no_devices"
                elif len(self._devices) == 1:
                    device = self._devices[0]
                    await self.async_set_unique_id(device["device_mac"])
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=device["device_name"],
                        data={
                            CONF_USERNAME: self._username,
                            CONF_PASSWORD: self._password,
                            CONF_DEVICE_MAC: device["device_mac"],
                            "device_type": device.get("device_type", DEVICE_TYPE_S10),
                        },
                    )
                else:
                    return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the device picker step (multiple S10s)."""
        if user_input is not None:
            device_mac = user_input[CONF_DEVICE_MAC]
            device = next(
                (d for d in self._devices if d["device_mac"] == device_mac), None
            )
            if device:
                await self.async_set_unique_id(device_mac)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=device["device_name"],
                    data={
                        CONF_USERNAME: self._username,
                        CONF_PASSWORD: self._password,
                        CONF_DEVICE_MAC: device_mac,
                        "device_type": device.get("device_type", DEVICE_TYPE_S10),
                    },
                )

        device_options = {
            d["device_mac"]: f"{d['device_name']} ({d['device_mac']})"
            for d in self._devices
        }
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE_MAC): vol.In(device_options)}
            ),
        )
