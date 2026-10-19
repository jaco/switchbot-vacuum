"""Config flow for SwitchBot Vacuum."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import (
    CONF_DEVICE_MAC,
    CONF_PASSWORD,
    CONF_PRODUCT_KEY,
    CONF_USERNAME,
    DEVICE_TYPE_S10,
    DOMAIN,
)
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
                            CONF_PRODUCT_KEY: device.get("product_key", ""),
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
        """Handle the device picker step (multiple vacuums)."""
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
                        CONF_PRODUCT_KEY: device.get("product_key", ""),
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

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Recover the existing entry after its password stops working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Request the current password for the existing account."""
        return await self._async_password_form(
            "reauth_confirm", self._get_reauth_entry(), user_input
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Update the password without replacing the device or its entities."""
        return await self._async_password_form(
            "reconfigure", self._get_reconfigure_entry(), user_input
        )

    async def _async_password_form(
        self, step_id: str, entry: config_entries.ConfigEntry,
        user_input: dict[str, Any] | None,
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            credentials = {
                CONF_USERNAME: entry.data[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            try:
                coordinator = SwitchBotS10Coordinator(self.hass, None)
                coordinator.entry = type("Entry", (), {"data": credentials})()
                await coordinator.async_login()
                devices = await coordinator.async_discover_devices()
            except ConfigEntryAuthFailed:
                errors["base"] = "invalid_auth"
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                selected = next(
                    (d for d in devices if d["device_mac"] == entry.data[CONF_DEVICE_MAC]), None
                )
                if selected is None:
                    errors["base"] = "device_not_found"
                else:
                    await self.async_set_unique_id(selected["device_mac"])
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(
                        entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                    )
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )
