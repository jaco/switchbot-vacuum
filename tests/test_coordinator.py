"""Tests for the SwitchBot S10 coordinator."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientSession

from custom_components.switchbot_vacuum.coordinator import SwitchBotS10Coordinator


@pytest.fixture(autouse=True)
def patch_frame_helper():
    """Patch HA frame helper so DataUpdateCoordinator can initialize."""
    with patch("homeassistant.helpers.frame.report_usage"):
        yield


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance."""
    hass = MagicMock()
    hass.data = {}
    return hass


@pytest.fixture
def mock_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.data = {"username": "test@test.com", "password": "testpass", "device_mac": "AABBCCDDEEFF"}
    entry.entry_id = "test_entry_id"
    return entry


def _make_response(data: dict, status: int = 200):
    """Create a mock aiohttp response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=data)
    return resp


def _patch_session(response):
    """Create a patched aiohttp.ClientSession context manager."""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.post = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=response),
        __aexit__=AsyncMock(return_value=False),
    ))
    return patch("aiohttp.ClientSession", return_value=mock_session)


class TestLogin:
    """Test login functionality."""

    @pytest.mark.asyncio
    async def test_login_success(self, mock_hass, mock_entry):
        """Test successful login returns access token."""
        resp = _make_response({
            "body": {
                "access_token": "test_jwt_token",
                "refresh_token": "test_refresh",
            }
        })
        with _patch_session(resp):
            coordinator = SwitchBotS10Coordinator(mock_hass, mock_entry)
            await coordinator.async_login()
            assert coordinator.access_token == "test_jwt_token"

    @pytest.mark.asyncio
    async def test_login_failure_raises(self, mock_hass, mock_entry):
        """Test login with bad credentials raises."""
        resp = _make_response({"statusCode": 401, "message": "unauthorized"})
        with _patch_session(resp):
            coordinator = SwitchBotS10Coordinator(mock_hass, mock_entry)
            with pytest.raises(Exception):
                await coordinator.async_login()


class TestDiscoverDevices:
    """Test device discovery."""

    @pytest.mark.asyncio
    async def test_discovers_multiple_s10s(self, mock_hass, mock_entry):
        """Test that discover_devices finds all S10 devices."""
        resp = _make_response({
            "body": {
                "Items": [
                    {
                        "device_mac": "AABBCCDDEEFF",
                        "device_name": "Floor Cleaning Robot S10 B6",
                        "device_detail": {"device_type": "WoSweeperOrigin"},
                        "userID": "user-123",
                        "groupID": "group-123",
                    },
                    {
                        "device_mac": "AABBCCDD",
                        "device_name": "Light",
                        "device_detail": {"device_type": "WoLight"},
                    },
                    {
                        "device_mac": "C0D1E2F30044",
                        "device_name": "Floor Cleaning Robot S10 44",
                        "device_detail": {"device_type": "WoSweeperOrigin"},
                        "userID": "user-123",
                        "groupID": "group-456",
                    },
                ]
            }
        })
        with _patch_session(resp):
            coordinator = SwitchBotS10Coordinator(mock_hass, mock_entry)
            coordinator.access_token = "fake_token"
            devices = await coordinator.async_discover_devices()

            assert len(devices) == 2
            assert devices[0]["device_mac"] == "AABBCCDDEEFF"
            assert devices[1]["device_mac"] == "C0D1E2F30044"

    @pytest.mark.asyncio
    async def test_discovers_single_s10(self, mock_hass, mock_entry):
        """Test discovery with single S10."""
        resp = _make_response({
            "body": {
                "Items": [
                    {
                        "device_mac": "AABBCCDDEEFF",
                        "device_name": "Floor Cleaning Robot S10 B6",
                        "device_detail": {"device_type": "WoSweeperOrigin"},
                        "userID": "user-123",
                        "groupID": "group-123",
                    },
                ]
            }
        })
        with _patch_session(resp):
            coordinator = SwitchBotS10Coordinator(mock_hass, mock_entry)
            coordinator.access_token = "fake_token"
            devices = await coordinator.async_discover_devices()

            assert len(devices) == 1
            assert devices[0]["device_name"] == "Floor Cleaning Robot S10 B6"


class TestGetProperties:
    """Test property fetching."""

    @pytest.mark.asyncio
    async def test_get_status_properties(self, mock_hass, mock_entry):
        """Test fetching status properties."""
        resp = _make_response({
            "resultCode": 100,
            "data": {
                "1003": {"id": 1003, "value": True},
                "1004": {"id": 1004, "value": 85},
                "1010": {"id": 1010, "value": 3},
                "1053": {"id": 1053, "value": {
                    "fan_level": 2, "times": 1,
                    "type": "sweep_mop", "water_level": 1,
                }},
                "1052": {"id": 1052, "value": {
                    "clean_area": 45, "clean_time": 30,
                    "duration": 1800, "total_area": 1,
                }},
            },
        })
        with _patch_session(resp):
            coordinator = SwitchBotS10Coordinator(mock_hass, mock_entry)
            coordinator.access_token = "fake_token"
            coordinator.device_mac = "AABBCCDDEEFF"
            props = await coordinator.async_get_properties([1003, 1004, 1010, 1053, 1052])

            assert props[1003] is True
            assert props[1004] == 85
            assert props[1010] == 3


class TestSendCommand:
    """Test command sending."""

    @pytest.mark.asyncio
    async def test_send_clean_rooms(self, mock_hass, mock_entry):
        """Test sending a clean_rooms command."""
        resp = _make_response({"resultCode": 100, "data": "CMD-UUID"})
        with _patch_session(resp):
            coordinator = SwitchBotS10Coordinator(mock_hass, mock_entry)
            coordinator.access_token = "fake_token"
            coordinator.device_mac = "AABBCCDDEEFF"
            coordinator._uuid = "test-uuid"
            result = await coordinator.async_send_command(
                1001,
                {"0": "clean_rooms", "1": {
                    "force_order": True,
                    "mode": {"fan_level": 1, "times": 1, "type": "mop", "water_level": 2},
                    "rooms": [{"room_id": "ROOM_013", "mode": {
                        "fan_level": 1, "times": 1, "type": "mop", "water_level": 2,
                    }}],
                }},
            )
            assert result["resultCode"] == 100
