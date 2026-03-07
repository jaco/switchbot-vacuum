"""Binary sensor entities for SwitchBot Vacuum."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ERROR_CODES, WORK_STATUS_FAULT
from .coordinator import SwitchBotS10Coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    coordinator: SwitchBotS10Coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SwitchBotVacuumProblem(coordinator)])


class SwitchBotVacuumProblem(
    CoordinatorEntity[SwitchBotS10Coordinator], BinarySensorEntity
):
    """Binary sensor that is ON when the vacuum has any error."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: SwitchBotS10Coordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_mac}_problem"
        self._attr_name = "Problem"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_mac)},
        )

    @property
    def is_on(self) -> bool:
        """Return True if there is an active error."""
        error_code = self.coordinator.data.get("error_code", 0)
        work_status = self.coordinator.data.get("work_status", 0)
        return error_code != 0 or work_status == WORK_STATUS_FAULT

    @property
    def extra_state_attributes(self) -> dict[str, str | int]:
        """Return error details."""
        error_code = self.coordinator.data.get("error_code", 0)
        error_type = ERROR_CODES.get(error_code, f"error_{error_code}")
        return {
            "error_code": error_code,
            "error_type": error_type,
        }
