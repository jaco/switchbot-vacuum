"""Tests for the SwitchBot S10 vacuum entity."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.switchbot_vacuum.const import (
    WORK_STATUS_CHARGE_DONE,
    WORK_STATUS_CHARGING,
    WORK_STATUS_CLEANING,
    WORK_STATUS_GO_CHARGE,
    WORK_STATUS_PAUSED,
    WORK_STATUS_STANDBY,
)
from custom_components.switchbot_vacuum.vacuum import SwitchBotS10Vacuum


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator with data."""
    coord = MagicMock()
    coord.data = {
        "online": True,
        "battery": 85,
        "work_status": WORK_STATUS_CHARGE_DONE,
        "error_code": 0,
        "clean_mode": {"fan_level": 2, "times": 1, "type": "sweep_mop", "water_level": 1},
        "clean_summary": {"clean_area": 45, "clean_time": 30, "duration": 1800},
        "firmware": "1.1.061",
        "rooms": {"ROOM_001": "Table", "ROOM_013": "Kitchen"},
    }
    coord.device_mac = "AABBCCDDEEFF"
    coord.device_name = "S10 B6"
    coord.async_send_command = AsyncMock(return_value={"resultCode": 100})
    coord.async_request_refresh = AsyncMock()
    return coord


class TestVacuumState:
    """Test vacuum state mapping."""

    def test_activity_docked_when_charging(self, mock_coordinator):
        """Test charging maps to DOCKED."""
        mock_coordinator.data["work_status"] = WORK_STATUS_CHARGING
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.activity.value == "docked"

    def test_activity_docked_when_charge_done(self, mock_coordinator):
        """Test charge done maps to DOCKED."""
        mock_coordinator.data["work_status"] = WORK_STATUS_CHARGE_DONE
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.activity.value == "docked"

    def test_activity_cleaning(self, mock_coordinator):
        """Test cleaning status maps to CLEANING."""
        mock_coordinator.data["work_status"] = WORK_STATUS_CLEANING
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.activity.value == "cleaning"

    def test_activity_paused(self, mock_coordinator):
        """Test paused status maps to PAUSED."""
        mock_coordinator.data["work_status"] = WORK_STATUS_PAUSED
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.activity.value == "paused"

    def test_activity_returning(self, mock_coordinator):
        """Test go charge maps to RETURNING."""
        mock_coordinator.data["work_status"] = WORK_STATUS_GO_CHARGE
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.activity.value == "returning"

    def test_activity_idle_when_standby(self, mock_coordinator):
        """Test standby maps to IDLE."""
        mock_coordinator.data["work_status"] = WORK_STATUS_STANDBY
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.activity.value == "idle"

    def test_battery_level(self, mock_coordinator):
        """Test battery level is read from data."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.battery_level == 85

    def test_fan_speed(self, mock_coordinator):
        """Test fan speed maps from fan_level."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        assert vac.fan_speed == "standard"

    def test_extra_state_attributes(self, mock_coordinator):
        """Test extra attributes include rooms and clean info."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        attrs = vac.extra_state_attributes
        assert attrs["water_level"] == 1
        assert attrs["clean_type"] == "sweep_mop"
        assert "rooms" in attrs
        assert attrs["rooms"]["ROOM_013"] == "Kitchen"


class TestVacuumCommands:
    """Test vacuum command methods."""

    @pytest.mark.asyncio
    async def test_start(self, mock_coordinator):
        """Test start sends clean_all."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_start()
        mock_coordinator.async_send_command.assert_called_once()
        args = mock_coordinator.async_send_command.call_args
        assert args[0][0] == 1001  # CMD_CLEAN
        assert args[0][1]["0"] == "clean_all"

    @pytest.mark.asyncio
    async def test_stop(self, mock_coordinator):
        """Test stop sends stop command."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_stop()
        args = mock_coordinator.async_send_command.call_args
        assert args[0][0] == 1009  # CMD_CONTROL
        assert args[0][1]["0"] == "stop"

    @pytest.mark.asyncio
    async def test_pause(self, mock_coordinator):
        """Test pause sends pause command."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_pause()
        args = mock_coordinator.async_send_command.call_args
        assert args[0][1]["0"] == "pause"

    @pytest.mark.asyncio
    async def test_return_to_base(self, mock_coordinator):
        """Test return to base sends go charge."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_return_to_base()
        args = mock_coordinator.async_send_command.call_args
        assert args[0][0] == 1008  # CMD_GO_CHARGE

    @pytest.mark.asyncio
    async def test_set_fan_speed(self, mock_coordinator):
        """Test set fan speed sends change mode."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_set_fan_speed("strong")
        args = mock_coordinator.async_send_command.call_args
        assert args[0][0] == 1043  # CMD_CHANGE_MODE
        assert args[0][1]["0"]["fan_level"] == 3

    @pytest.mark.asyncio
    async def test_clean_rooms_with_ids(self, mock_coordinator):
        """Test clean_rooms with room IDs."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_clean_rooms(
            rooms=["ROOM_013", "ROOM_008"],
            mode="mop",
            fan_level=1,
            water_level=2,
            times=1,
            force_order=True,
        )
        args = mock_coordinator.async_send_command.call_args
        assert args[0][0] == 1001
        params = args[0][1]
        assert params["0"] == "clean_rooms"
        assert len(params["1"]["rooms"]) == 2
        assert params["1"]["rooms"][0]["room_id"] == "ROOM_013"
        assert params["1"]["rooms"][0]["mode"]["type"] == "mop"


class TestRoomNameResolution:
    """Test that clean_rooms accepts room names, not just IDs."""

    @pytest.mark.asyncio
    async def test_resolve_room_names(self, mock_coordinator):
        """Test room names are resolved to IDs."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_clean_rooms(
            rooms=["Kitchen", "Table"],
            mode="mop",
            fan_level=1,
            water_level=2,
            times=1,
            force_order=True,
        )
        args = mock_coordinator.async_send_command.call_args
        rooms_sent = args[0][1]["1"]["rooms"]
        room_ids = [r["room_id"] for r in rooms_sent]
        assert "ROOM_013" in room_ids
        assert "ROOM_001" in room_ids

    @pytest.mark.asyncio
    async def test_mixed_names_and_ids(self, mock_coordinator):
        """Test mix of names and IDs."""
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_clean_rooms(
            rooms=["Kitchen", "ROOM_001"],
            mode="sweep_mop",
            fan_level=2,
            water_level=1,
            times=1,
            force_order=False,
        )
        args = mock_coordinator.async_send_command.call_args
        rooms_sent = args[0][1]["1"]["rooms"]
        room_ids = [r["room_id"] for r in rooms_sent]
        assert "ROOM_013" in room_ids
        assert "ROOM_001" in room_ids


class TestForceRefresh:
    """Test force_refresh service."""

    @pytest.mark.asyncio
    async def test_force_refresh(self, mock_coordinator):
        """Test force_refresh calls coordinator refresh methods."""
        mock_coordinator.async_refresh = AsyncMock()
        mock_coordinator.async_refresh_rooms = AsyncMock()
        vac = SwitchBotS10Vacuum(mock_coordinator)
        await vac.async_force_refresh()
        mock_coordinator.async_refresh_rooms.assert_called_once()
        mock_coordinator.async_refresh.assert_called_once()
