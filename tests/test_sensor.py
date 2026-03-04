"""Tests for the SwitchBot Vacuum room sensor entities."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.switchbot_vacuum.sensor import SwitchBotRoomSensor


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator with rooms."""
    coord = MagicMock()
    coord.data = {
        "rooms": {"ROOM_001": "Table", "ROOM_013": "Kitchen"},
    }
    coord.device_mac = "AABBCCDDEEFF"
    coord.device_name = "S10"
    return coord


class TestRoomSensor:
    """Test room sensor entity."""

    def test_sensor_name(self, mock_coordinator):
        """Test sensor name is room name."""
        sensor = SwitchBotRoomSensor(mock_coordinator, "ROOM_013", "Kitchen")
        assert sensor.name == "Kitchen"

    def test_sensor_unique_id(self, mock_coordinator):
        """Test unique_id includes device mac and room id."""
        sensor = SwitchBotRoomSensor(mock_coordinator, "ROOM_013", "Kitchen")
        assert sensor.unique_id == "AABBCCDDEEFF_room_ROOM_013"

    def test_native_value_is_room_name(self, mock_coordinator):
        """Test native value returns current room name."""
        sensor = SwitchBotRoomSensor(mock_coordinator, "ROOM_013", "Kitchen")
        assert sensor.native_value == "Kitchen"

    def test_native_value_updates_on_rename(self, mock_coordinator):
        """Test native value reflects renamed room."""
        sensor = SwitchBotRoomSensor(mock_coordinator, "ROOM_013", "Kitchen")
        mock_coordinator.data["rooms"]["ROOM_013"] = "Kuchnia"
        assert sensor.native_value == "Kuchnia"

    def test_extra_attributes_has_room_id(self, mock_coordinator):
        """Test extra attributes contain room_id."""
        sensor = SwitchBotRoomSensor(mock_coordinator, "ROOM_001", "Table")
        assert sensor.extra_state_attributes["room_id"] == "ROOM_001"

    def test_icon(self, mock_coordinator):
        """Test sensor icon."""
        sensor = SwitchBotRoomSensor(mock_coordinator, "ROOM_001", "Table")
        assert sensor.icon == "mdi:floor-plan"
