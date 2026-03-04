"""Tests for the SwitchBot Vacuum room button entities."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.switchbot_vacuum.button import SwitchBotRoomButton


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator with rooms."""
    coord = MagicMock()
    coord.data = {
        "rooms": {"ROOM_001": "Table", "ROOM_013": "Kitchen"},
        "clean_mode": {"fan_level": 2, "times": 1, "type": "sweep_mop", "water_level": 1},
    }
    coord.device_mac = "AABBCCDDEEFF"
    coord.device_name = "S10"
    coord.async_send_command = AsyncMock(return_value={"resultCode": 100})
    coord.async_request_refresh = AsyncMock()
    return coord


class TestRoomButton:
    """Test room button entity."""

    def test_button_attributes(self, mock_coordinator):
        """Test button has correct name and unique_id."""
        btn = SwitchBotRoomButton(mock_coordinator, "ROOM_013", "Kitchen")
        assert btn.name == "Clean Kitchen"
        assert btn.unique_id == "AABBCCDDEEFF_room_ROOM_013"
        assert btn.icon == "mdi:broom"

    @pytest.mark.asyncio
    async def test_press_sends_clean_rooms(self, mock_coordinator):
        """Test pressing button sends clean command for that room."""
        btn = SwitchBotRoomButton(mock_coordinator, "ROOM_013", "Kitchen")
        await btn.async_press()

        args = mock_coordinator.async_send_command.call_args
        assert args[0][0] == 1001  # CMD_CLEAN
        params = args[0][1]
        assert params["0"] == "clean_rooms"
        assert len(params["1"]["rooms"]) == 1
        assert params["1"]["rooms"][0]["room_id"] == "ROOM_013"
        assert params["1"]["rooms"][0]["mode"]["fan_level"] == 2

    @pytest.mark.asyncio
    async def test_press_uses_current_mode(self, mock_coordinator):
        """Test button uses current clean_mode settings."""
        mock_coordinator.data["clean_mode"] = {
            "fan_level": 3, "times": 2, "type": "mop", "water_level": 2,
        }
        btn = SwitchBotRoomButton(mock_coordinator, "ROOM_001", "Table")
        await btn.async_press()

        args = mock_coordinator.async_send_command.call_args
        mode = args[0][1]["1"]["rooms"][0]["mode"]
        assert mode["fan_level"] == 3
        assert mode["type"] == "mop"
        assert mode["water_level"] == 2
        assert mode["times"] == 2
