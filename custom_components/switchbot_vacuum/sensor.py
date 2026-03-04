"""Sensor entities for SwitchBot Vacuum rooms."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SwitchBotS10Coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up room sensor entities."""
    coordinator: SwitchBotS10Coordinator = hass.data[DOMAIN][entry.entry_id]

    known_room_ids: set[str] = set()

    @callback
    def _async_add_new_rooms() -> None:
        """Add sensor entities for newly discovered rooms."""
        rooms = coordinator.data.get("rooms", {})
        new_entities = []
        for room_id, room_name in rooms.items():
            if room_id not in known_room_ids:
                known_room_ids.add(room_id)
                new_entities.append(
                    SwitchBotRoomSensor(coordinator, room_id, room_name)
                )
        if new_entities:
            async_add_entities(new_entities)

    _async_add_new_rooms()
    coordinator.async_add_listener(_async_add_new_rooms)


class SwitchBotRoomSensor(CoordinatorEntity[SwitchBotS10Coordinator], SensorEntity):
    """Sensor representing a room known to the vacuum."""

    def __init__(
        self,
        coordinator: SwitchBotS10Coordinator,
        room_id: str,
        room_name: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._room_id = room_id
        self._attr_unique_id = f"{coordinator.device_mac}_room_{room_id}"
        self._attr_name = room_name
        self._attr_icon = "mdi:floor-plan"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_mac)},
        )

    @property
    def native_value(self) -> str:
        """Return room name (updates if renamed in app)."""
        rooms = self.coordinator.data.get("rooms", {})
        return rooms.get(self._room_id, self._room_id)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return room ID as attribute."""
        return {"room_id": self._room_id}
