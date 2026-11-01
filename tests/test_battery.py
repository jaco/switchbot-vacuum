"""Battery migration regression tests against Home Assistant's real API."""
from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE

from custom_components.switchbot_vacuum import sensor as platform
from custom_components.switchbot_vacuum.const import (
    DEVICE_TYPE_K10,
    DEVICE_TYPE_K10PRO,
    DEVICE_TYPE_S10,
    DOMAIN,
)
from custom_components.switchbot_vacuum.sensor import SwitchBotVacuumBattery
from custom_components.switchbot_vacuum.vacuum import SwitchBotS10Vacuum


@pytest.fixture
def coordinator():
    coordinator = MagicMock()
    coordinator.device_mac = "AABBCCDDEEFF"
    coordinator.device_name = "Test vacuum"
    coordinator.data = {"battery": 85, "rooms": {}, "firmware": "test"}
    coordinator.entry.data = {"device_type": DEVICE_TYPE_S10}
    coordinator.last_update_success = True
    return coordinator


def test_battery_is_a_sensor_on_the_same_device(coordinator):
    """The battery has a stable identity and HA battery semantics."""
    battery = SwitchBotVacuumBattery(coordinator)
    vacuum = SwitchBotS10Vacuum(coordinator)
    assert battery.device_info["identifiers"] == vacuum.device_info["identifiers"]
    assert battery.unique_id == "AABBCCDDEEFF_battery"
    assert battery.device_class is SensorDeviceClass.BATTERY
    assert battery.native_unit_of_measurement == PERCENTAGE
    assert battery.state_class is SensorStateClass.MEASUREMENT
    assert battery.has_entity_name
    assert "battery_level" not in type(vacuum).__dict__


def test_battery_tracks_coordinator_updates_and_unavailability(coordinator):
    battery = SwitchBotVacuumBattery(coordinator)
    assert battery.native_value == 85
    coordinator.data["battery"] = 42
    assert battery.native_value == 42
    coordinator.data.pop("battery")
    assert battery.native_value is None
    coordinator.last_update_success = False
    assert not battery.available


@pytest.mark.parametrize("device_type", [DEVICE_TYPE_S10, DEVICE_TYPE_K10, DEVICE_TYPE_K10PRO])
async def test_platform_adds_one_battery_for_each_model(coordinator, device_type):
    """Setup registers a battery for every supported family without device calls."""
    entry = MagicMock()
    entry.entry_id = "test-entry"
    entry.data = {"device_type": device_type}
    coordinator.entry = entry
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coordinator}}
    added = []
    await platform.async_setup_entry(hass, entry, added.extend)
    assert len([entity for entity in added if isinstance(entity, SwitchBotVacuumBattery)]) == 1
