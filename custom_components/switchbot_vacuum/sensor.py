"""Sensor entities for SwitchBot Vacuum rooms."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_TYPE_K10, DOMAIN
from .coordinator import SwitchBotS10Coordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleanSummaryDescription(SensorEntityDescription):
    """Description for clean summary sensor."""
    summary_key: str = ""
    scale: float = 1.0


CLEAN_SUMMARY_SENSORS: list[CleanSummaryDescription] = [
    CleanSummaryDescription(
        key="clean_area",
        summary_key="clean_area",
        name="Clean Area",
        native_unit_of_measurement="m²",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:floor-plan",
        scale=1.0,
    ),
    CleanSummaryDescription(
        key="total_area",
        summary_key="total_area",
        name="Total Area",
        native_unit_of_measurement="m²",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:floor-plan",
        scale=1.0,
    ),
    CleanSummaryDescription(
        key="clean_time",
        summary_key="clean_time_ms",
        name="Clean Time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        scale=0.001,
    ),
    CleanSummaryDescription(
        key="duration",
        summary_key="duration",
        name="Session Duration",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        scale=0.001,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up room sensor entities."""
    coordinator: SwitchBotS10Coordinator = hass.data[DOMAIN][entry.entry_id]
    device_type = entry.data.get("device_type", "")

    entities: list[SensorEntity] = []

    if device_type != DEVICE_TYPE_K10:
        entities.extend(
            SwitchBotCleanSummarySensor(coordinator, desc)
            for desc in CLEAN_SUMMARY_SENSORS
        )

    if entities:
        async_add_entities(entities)

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
        self._attr_name = room_id
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


class SwitchBotCleanSummarySensor(CoordinatorEntity[SwitchBotS10Coordinator], SensorEntity):
    """Sensor for S10 clean summary metrics."""

    entity_description: CleanSummaryDescription

    def __init__(
        self,
        coordinator: SwitchBotS10Coordinator,
        description: CleanSummaryDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_mac}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_mac)},
        )

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        summary = self.coordinator.data.get("clean_summary", {})
        if not isinstance(summary, dict):
            return None
        raw = summary.get(self.entity_description.summary_key)
        if raw is None:
            return None
        return round(raw * self.entity_description.scale, 1)
