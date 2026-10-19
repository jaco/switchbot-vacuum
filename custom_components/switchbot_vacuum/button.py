"""K10+ base station controls."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
        async_add_entities([SwitchBotEmptyDustbin(coordinator)])


class SwitchBotEmptyDustbin(CoordinatorEntity[SwitchBotS10Coordinator], ButtonEntity):
    """Manually empty a docked K10+ into its base station."""

    _attr_has_entity_name = True
    _attr_name = "Empty dustbin"
    _attr_icon = "mdi:delete-empty"

    def __init__(self, coordinator: SwitchBotS10Coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_mac}_empty_dustbin"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.device_mac)})

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.get("k10_controls_available", False)

    async def async_press(self) -> None:
        await self.coordinator.async_k10_control("empty_dustbin")
