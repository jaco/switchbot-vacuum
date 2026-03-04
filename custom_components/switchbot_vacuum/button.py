"""Button entities for SwitchBot Vacuum rooms."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CMD_CLEAN, DOMAIN
from .coordinator import SwitchBotS10Coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up room button entities."""
    coordinator: SwitchBotS10Coordinator = hass.data[DOMAIN][entry.entry_id]

    known_room_ids: set[str] = set()

    @callback
    def _async_add_new_rooms() -> None:
        """Add button entities for newly discovered rooms."""
        rooms = coordinator.data.get("rooms", {})
        new_entities = []
        for room_id, room_name in rooms.items():
            if room_id not in known_room_ids:
                known_room_ids.add(room_id)
                new_entities.append(
                    SwitchBotRoomButton(coordinator, room_id, room_name)
                )
        if new_entities:
            async_add_entities(new_entities)

    _async_add_new_rooms()
    coordinator.async_add_listener(_async_add_new_rooms)


class SwitchBotRoomButton(CoordinatorEntity[SwitchBotS10Coordinator], ButtonEntity):
    """Button to clean a specific room."""

    def __init__(
        self,
        coordinator: SwitchBotS10Coordinator,
        room_id: str,
        room_name: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._room_id = room_id
        self._room_name = room_name
        self._attr_unique_id = f"{coordinator.device_mac}_room_{room_id}"
        self._attr_name = f"Clean {room_name}"
        self._attr_icon = "mdi:broom"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_mac)},
        )

    async def async_press(self) -> None:
        """Clean this room with current default settings."""
        mode = self.coordinator.data.get("clean_mode", {})
        if not isinstance(mode, dict):
            mode = {}
        room_mode = {
            "fan_level": mode.get("fan_level", 1),
            "times": mode.get("times", 1),
            "type": mode.get("type", "sweep_mop"),
            "water_level": mode.get("water_level", 1),
        }
        await self.coordinator.async_send_command(CMD_CLEAN, {
            "0": "clean_rooms",
            "1": {
                "force_order": True,
                "mode": room_mode,
                "rooms": [{"room_id": self._room_id, "mode": dict(room_mode)}],
            },
        })
        await self.coordinator.async_request_refresh()
