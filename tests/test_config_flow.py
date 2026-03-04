"""Tests for the SwitchBot S10 config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.switchbot_vacuum.config_flow import SwitchBotS10ConfigFlow
from custom_components.switchbot_vacuum.const import DOMAIN


@pytest.fixture(autouse=True)
def patch_frame_helper():
    """Patch HA frame helper."""
    with patch("homeassistant.helpers.frame.report_usage"):
        yield


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance."""
    hass = MagicMock()
    hass.data = {}
    return hass


def _make_flow(mock_hass) -> SwitchBotS10ConfigFlow:
    """Create a config flow instance with mocked hass."""
    flow = SwitchBotS10ConfigFlow()
    flow.hass = mock_hass
    flow.context = {"source": "user"}
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    return flow


class TestUserStep:
    """Test user step of config flow."""

    @pytest.mark.asyncio
    async def test_user_form_shows(self, mock_hass):
        """Test that the user form is served."""
        flow = _make_flow(mock_hass)
        result = await flow.async_step_user()

        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_single_device_creates_entry(self, mock_hass):
        """Test successful config flow with single device creates entry."""
        with patch(
            "custom_components.switchbot_vacuum.config_flow.SwitchBotS10Coordinator"
        ) as mock_coord_cls:
            mock_coord = AsyncMock()
            mock_coord.async_login = AsyncMock()
            mock_coord.async_discover_devices = AsyncMock(return_value=[
                {
                    "device_mac": "AABBCCDDEEFF",
                    "device_name": "Floor Cleaning Robot S10 B6",
                    "user_id": "user-123",
                    "group_id": "group-123",
                }
            ])
            mock_coord_cls.return_value = mock_coord

            flow = _make_flow(mock_hass)
            result = await flow.async_step_user(
                {"username": "test@test.com", "password": "testpass"}
            )

            assert result["type"] == "create_entry"
            assert result["title"] == "Floor Cleaning Robot S10 B6"
            assert result["data"]["username"] == "test@test.com"
            assert result["data"]["device_mac"] == "AABBCCDDEEFF"

    @pytest.mark.asyncio
    async def test_auth_error(self, mock_hass):
        """Test config flow handles auth failure."""
        with patch(
            "custom_components.switchbot_vacuum.config_flow.SwitchBotS10Coordinator"
        ) as mock_coord_cls:
            mock_coord = AsyncMock()
            mock_coord.async_login = AsyncMock(side_effect=Exception("auth failed"))
            mock_coord_cls.return_value = mock_coord

            flow = _make_flow(mock_hass)
            result = await flow.async_step_user(
                {"username": "bad@test.com", "password": "wrong"}
            )

            assert result["type"] == "form"
            assert result["errors"] == {"base": "invalid_auth"}

    @pytest.mark.asyncio
    async def test_no_devices_error(self, mock_hass):
        """Test config flow handles no S10 devices found."""
        with patch(
            "custom_components.switchbot_vacuum.config_flow.SwitchBotS10Coordinator"
        ) as mock_coord_cls:
            mock_coord = AsyncMock()
            mock_coord.async_login = AsyncMock()
            mock_coord.async_discover_devices = AsyncMock(return_value=[])
            mock_coord_cls.return_value = mock_coord

            flow = _make_flow(mock_hass)
            result = await flow.async_step_user(
                {"username": "test@test.com", "password": "testpass"}
            )

            assert result["type"] == "form"
            assert result["errors"] == {"base": "no_devices"}


class TestDeviceStep:
    """Test device picker step for multiple vacuums."""

    @pytest.mark.asyncio
    async def test_multiple_devices_shows_picker(self, mock_hass):
        """Test multiple S10 devices triggers device step."""
        with patch(
            "custom_components.switchbot_vacuum.config_flow.SwitchBotS10Coordinator"
        ) as mock_coord_cls:
            mock_coord = AsyncMock()
            mock_coord.async_login = AsyncMock()
            mock_coord.async_discover_devices = AsyncMock(return_value=[
                {
                    "device_mac": "AABBCCDDEEFF",
                    "device_name": "S10 B6",
                    "user_id": "user-123",
                    "group_id": "group-123",
                },
                {
                    "device_mac": "C0D1E2F30044",
                    "device_name": "S10 44",
                    "user_id": "user-123",
                    "group_id": "group-456",
                },
            ])
            mock_coord_cls.return_value = mock_coord

            flow = _make_flow(mock_hass)
            result = await flow.async_step_user(
                {"username": "test@test.com", "password": "testpass"}
            )

            assert result["type"] == "form"
            assert result["step_id"] == "device"

    @pytest.mark.asyncio
    async def test_device_picker_creates_entry(self, mock_hass):
        """Test selecting a device from picker creates entry."""
        flow = _make_flow(mock_hass)
        flow._username = "test@test.com"
        flow._password = "testpass"
        flow._devices = [
            {
                "device_mac": "AABBCCDDEEFF",
                "device_name": "S10 B6",
                "user_id": "user-123",
                "group_id": "group-123",
            },
            {
                "device_mac": "C0D1E2F30044",
                "device_name": "S10 44",
                "user_id": "user-123",
                "group_id": "group-456",
            },
        ]

        result = await flow.async_step_device(
            {"device_mac": "C0D1E2F30044"}
        )

        assert result["type"] == "create_entry"
        assert result["title"] == "S10 44"
        assert result["data"]["device_mac"] == "C0D1E2F30044"
