"""Vacuum entity for SwitchBot Vacuum."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CMD_CHANGE_MODE,
    CMD_CLEAN,
    CMD_CONTROL,
    CMD_GO_CHARGE,
    DEVICE_TYPE_K10,
    DEVICE_TYPE_S10,
    DEVICE_TYPE_TO_MODEL,
    DOMAIN,
    FAN_SPEED_LIST,
    FAN_SPEEDS,
    K10_FAN_LEVEL_TO_SPEED,
    K10_FAN_SPEED_LIST,
    K10_FAN_SPEEDS,
    WORK_STATUS_CHARGE_DONE,
    WORK_STATUS_CHARGING,
    WORK_STATUS_CLEANING,
    WORK_STATUS_GO_CHARGE,
    WORK_STATUS_PAUSED,
    WORK_STATUS_STANDBY,
)
from .coordinator import SwitchBotS10Coordinator

_LOGGER = logging.getLogger(__name__)

WORK_STATUS_TO_ACTIVITY = {
    WORK_STATUS_STANDBY: VacuumActivity.IDLE,
    WORK_STATUS_CHARGING: VacuumActivity.DOCKED,
    WORK_STATUS_CHARGE_DONE: VacuumActivity.DOCKED,
    WORK_STATUS_PAUSED: VacuumActivity.PAUSED,
    WORK_STATUS_GO_CHARGE: VacuumActivity.RETURNING,
    WORK_STATUS_CLEANING: VacuumActivity.CLEANING,
}

FAN_LEVEL_TO_SPEED = {v: k for k, v in FAN_SPEEDS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up vacuum entity."""
    coordinator: SwitchBotS10Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SwitchBotS10Vacuum(coordinator)])

    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        "clean_rooms",
        {
            vol.Required("rooms"): [str],
            vol.Optional("mode", default="sweep_mop"): vol.In(
                ["sweep", "mop", "sweep_mop"]
            ),
            vol.Optional("fan_level", default=1): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=4)
            ),
            vol.Optional("water_level", default=1): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=3)
            ),
            vol.Optional("times", default=1): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=2)
            ),
            vol.Optional("force_order", default=True): bool,
        },
        "async_clean_rooms",
    )

    platform.async_register_entity_service(
        "force_refresh",
        {},
        "async_force_refresh",
    )


class SwitchBotS10Vacuum(CoordinatorEntity[SwitchBotS10Coordinator], StateVacuumEntity):
    """SwitchBot Vacuum vacuum entity."""

    _attr_supported_features = (
        VacuumEntityFeature.STATE
        | VacuumEntityFeature.START
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.FAN_SPEED
        | VacuumEntityFeature.SEND_COMMAND
        | VacuumEntityFeature.BATTERY
    )
    def __init__(self, coordinator: SwitchBotS10Coordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_mac}_vacuum"
        self._attr_name = coordinator.device_name or "SwitchBot Vacuum"
        device_type = coordinator.entry.data.get("device_type", DEVICE_TYPE_S10)
        self._is_k10 = device_type == DEVICE_TYPE_K10
        self._attr_fan_speed_list = K10_FAN_SPEED_LIST if self._is_k10 else FAN_SPEED_LIST
        self._k10_local_fan_speed: str | None = None  # tracks last-set speed (getInfo is stale)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_mac)},
            name=coordinator.device_name or "SwitchBot Vacuum",
            manufacturer="SwitchBot",
            model=DEVICE_TYPE_TO_MODEL.get(device_type, device_type),
            sw_version=coordinator.data.get("firmware", ""),
        )

    @property
    def activity(self) -> VacuumActivity:
        """Return current activity."""
        status = self.coordinator.data.get("work_status", WORK_STATUS_STANDBY)
        return WORK_STATUS_TO_ACTIVITY.get(status, VacuumActivity.IDLE)

    @property
    def battery_level(self) -> int | None:
        """Return battery level."""
        return self.coordinator.data.get("battery")

    @property
    def fan_speed(self) -> str | None:
        """Return current fan speed."""
        if self._is_k10:
            # getInfo returns stale SuctionPowLevel — use locally tracked value if available
            if self._k10_local_fan_speed is not None:
                return self._k10_local_fan_speed
            mode = self.coordinator.data.get("clean_mode", {})
            level = mode.get("fan_level", 0) if isinstance(mode, dict) else 0
            return K10_FAN_LEVEL_TO_SPEED.get(level, "quiet")
        mode = self.coordinator.data.get("clean_mode", {})
        level = mode.get("fan_level", 1) if isinstance(mode, dict) else 1
        return FAN_LEVEL_TO_SPEED.get(level, "quiet")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        mode = self.coordinator.data.get("clean_mode", {})
        summary = self.coordinator.data.get("clean_summary", {})
        attrs: dict[str, Any] = {}

        if isinstance(mode, dict):
            attrs["water_level"] = mode.get("water_level", 1)
            attrs["clean_type"] = mode.get("type", "sweep_mop")
            attrs["times"] = mode.get("times", 1)

        if isinstance(summary, dict):
            attrs["last_clean_area"] = summary.get("clean_area", 0)
            attrs["last_clean_time"] = summary.get("clean_time", 0)

        attrs["rooms"] = self.coordinator.data.get("rooms", {})
        return attrs

    async def async_start(self) -> None:
        """Start cleaning."""
        if self._is_k10:
            await self.coordinator.async_send_action(
                "StartDefaultClean", {"CleanTimes": 1}
            )
        else:
            mode = self.coordinator.data.get("clean_mode", {})
            if not isinstance(mode, dict):
                mode = {}
            await self.coordinator.async_send_command(CMD_CLEAN, {
                "0": "clean_all",
                "1": {
                    "force_order": False,
                    "mode": {
                        "fan_level": mode.get("fan_level", 1),
                        "times": mode.get("times", 1),
                        "type": mode.get("type", "sweep_mop"),
                        "water_level": mode.get("water_level", 1),
                    },
                },
            })
        await self.coordinator.async_request_refresh()

    async def async_stop(self, **kwargs: Any) -> None:
        """Stop cleaning."""
        if self._is_k10:
            await self.coordinator.async_send_action("PauseRobot")
        else:
            await self.coordinator.async_send_command(CMD_CONTROL, {"0": "stop"})
        await self.coordinator.async_request_refresh()

    async def async_pause(self) -> None:
        """Pause cleaning."""
        if self._is_k10:
            await self.coordinator.async_send_action("PauseRobot")
        else:
            await self.coordinator.async_send_command(CMD_CONTROL, {"0": "pause"})
        await self.coordinator.async_request_refresh()

    async def async_return_to_base(self, **kwargs: Any) -> None:
        """Return to charging base."""
        if self._is_k10:
            await self.coordinator.async_send_action("ReturnChargeBase")
        else:
            await self.coordinator.async_send_command(CMD_GO_CHARGE, {})
        await self.coordinator.async_request_refresh()

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        """Set fan speed."""
        if self._is_k10:
            level = K10_FAN_SPEEDS.get(fan_speed, 0)
            await self.coordinator.async_send_action(
                "SetSuctionPowLevelWithMode", {"Level": level}
            )
            self._k10_local_fan_speed = fan_speed
            self.async_write_ha_state()
        else:
            level = FAN_SPEEDS.get(fan_speed, 1)
            mode = self.coordinator.data.get("clean_mode", {})
            if not isinstance(mode, dict):
                mode = {}
            await self.coordinator.async_send_command(CMD_CHANGE_MODE, {
                "0": {
                    "fan_level": level,
                    "times": mode.get("times", 1),
                    "type": mode.get("type", "sweep_mop"),
                    "water_level": mode.get("water_level", 1),
                },
            })
        await self.coordinator.async_request_refresh()

    async def async_send_command(
        self, command: str, params: dict[str, Any] | list[Any] | None = None, **kwargs: Any
    ) -> None:
        """Send a raw command."""
        if params and isinstance(params, dict):
            func_id = params.get("function_id", CMD_CLEAN)
            cmd_params = params.get("params", {})
            await self.coordinator.async_send_command(func_id, cmd_params)

    async def async_clean_rooms(
        self,
        rooms: list[str],
        mode: str = "sweep_mop",
        fan_level: int = 1,
        water_level: int = 1,
        times: int = 1,
        force_order: bool = True,
    ) -> None:
        """Clean specific rooms. Accepts room IDs or names."""
        room_map = self.coordinator.data.get("rooms", {})
        name_to_id = {v: k for k, v in room_map.items()}

        resolved = []
        for room in rooms:
            if room.startswith("ROOM_"):
                resolved.append(room)
            elif room in name_to_id:
                resolved.append(name_to_id[room])
            else:
                _LOGGER.warning("Unknown room: %s", room)
                resolved.append(room)

        room_mode = {
            "fan_level": fan_level,
            "times": times,
            "type": mode,
            "water_level": water_level,
        }
        room_list = [
            {"room_id": r, "mode": dict(room_mode)} for r in resolved
        ]
        await self.coordinator.async_send_command(CMD_CLEAN, {
            "0": "clean_rooms",
            "1": {
                "force_order": force_order,
                "mode": room_mode,
                "rooms": room_list,
            },
        })
        await self.coordinator.async_request_refresh()

    async def async_force_refresh(self) -> None:
        """Force refresh status and room data."""
        await self.coordinator.async_refresh_rooms()
        await self.coordinator.async_refresh()
