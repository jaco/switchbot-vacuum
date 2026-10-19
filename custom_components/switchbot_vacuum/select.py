"""K10+ vacuum and mop selection."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_TYPE_K10, DOMAIN
from .coordinator import SwitchBotS10Coordinator
from .k10_api import WONDER


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if entry.data.get("device_type") == DEVICE_TYPE_K10 and (
        coordinator.wonderlab_endpoint or ""
    ).rstrip("/") == WONDER:
        async_add_entities([SwitchBotCleaningMode(coordinator)])


class SwitchBotCleaningMode(CoordinatorEntity[SwitchBotS10Coordinator], SelectEntity):
    """Select a cleaning mode without starting or stopping a task."""

    _attr_has_entity_name = True
    _attr_name = "Cleaning mode"
    _attr_icon = "mdi:robot-vacuum"

    def __init__(self, coordinator: SwitchBotS10Coordinator) -> None:
        super().__init__(coordinator)
        self._attr_options = ["vacuum", "mop"]
        self._attr_unique_id = f"{coordinator.device_mac}_cleaning_mode"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.device_mac)})

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.get("k10_controls_available", False)

    @property
    def current_option(self) -> str | None:
        mode = self.coordinator.data.get("clean_mode", {}).get("type")
        return {"sweep": "vacuum", "mop": "mop"}.get(mode)

    async def async_select_option(self, option: str) -> None:
        if option not in self._attr_options:
            raise HomeAssistantError("Select vacuum or mop")
        await self.coordinator.async_k10_control("mode", "sweep" if option == "vacuum" else "mop")
