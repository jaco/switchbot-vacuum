"""Cloud failures must not copy response bodies into HA errors or logs.

Run in a Home Assistant Python environment with:
python -m unittest discover -s tests -p test_cloud_error_privacy.py
All HTTP calls and device actions are fakes.
"""

import json
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.switchbot_vacuum import coordinator as module
from custom_components.switchbot_vacuum.const import DEVICE_TYPE_K10PRO


@contextmanager
def cloud_response(payload):
    response = MagicMock()
    response.json = AsyncMock(return_value=payload)
    request = AsyncMock()
    request.__aenter__.return_value = response
    session = MagicMock()
    session.post.return_value = request
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    # Support both the original per-request session and HA-managed sessions.
    with (
        patch.object(module.aiohttp, "ClientSession", return_value=session),
        patch.object(module, "async_get_clientsession", return_value=session, create=True),
    ):
        yield


class CloudErrorPrivacyTests(unittest.IsolatedAsyncioTestCase):
    def coordinator(self, *, device_type=None):
        coordinator = object.__new__(module.SwitchBotS10Coordinator)
        coordinator.hass = MagicMock()
        coordinator.entry = SimpleNamespace(data={"device_type": device_type})
        coordinator.device_mac = "fake-device"
        coordinator.wonderlab_endpoint = "https://example.invalid"
        coordinator.access_token = "fake-request-token"
        coordinator._uuid = "fake-installation"
        coordinator._rooms = {}
        coordinator._last_room_refresh = 0
        return coordinator

    async def test_property_failure_excludes_private_response_fields(self):
        coordinator = self.coordinator()
        payload = {
            "resultCode": 500,
            "message": "fake-private-email@example.invalid",
            "data": {"access_token": "fake-private-response-token"},
        }
        with cloud_response(payload), self.assertRaises(module.UpdateFailed) as error:
            await coordinator.async_get_properties([1004])
        self.assertEqual(str(error.exception), "Property fetch failed (resultCode 500)")

    async def test_status_failure_excludes_signed_urls(self):
        coordinator = self.coordinator()
        payload = {
            "statusCode": 190,
            "body": {"url": "https://storage.invalid/map?signature=fake-private-signature"},
        }
        with cloud_response(payload), self.assertRaises(module.UpdateFailed) as error:
            await coordinator.async_get_k10_status()
        self.assertEqual(str(error.exception), "K10+ getstatus failed (statusCode 190)")

    async def test_schedule_failure_excludes_private_response_fields(self):
        coordinator = self.coordinator(device_type=DEVICE_TYPE_K10PRO)
        coordinator.async_send_action = AsyncMock(return_value={
            "statusCode": 401, "body": {"token": "fake-private-schedule-token"},
        })
        with self.assertLogs(module._LOGGER, level="WARNING") as logs:
            await coordinator.async_refresh_k10_rooms()
        self.assertEqual(logs.records[0].getMessage(),
                         "GetCleanPolicyList failed (statusCode 401)")

    async def test_property_failure_does_not_log_untrusted_status_values(self):
        for value in ("fake-secret-status", {"token": "fake-secret"}, ["fake-secret"], True):
            with self.subTest(value=value):
                coordinator = self.coordinator()
                with cloud_response({"resultCode": value}), self.assertRaises(module.UpdateFailed) as error:
                    await coordinator.async_get_properties([1004])
                self.assertEqual(str(error.exception), "Property fetch failed (resultCode unknown)")

    async def test_status_failure_does_not_log_untrusted_status_values(self):
        for value in ("fake-secret-status", {"token": "fake-secret"}, ["fake-secret"], True):
            with self.subTest(value=value):
                coordinator = self.coordinator()
                with cloud_response({"statusCode": value}), self.assertRaises(module.UpdateFailed) as error:
                    await coordinator.async_get_k10_status()
                self.assertEqual(str(error.exception), "K10+ getstatus failed (statusCode unknown)")

    async def test_schedule_failure_does_not_log_untrusted_status_values(self):
        for value in ("fake-secret-status", {"token": "fake-secret"}, ["fake-secret"], True):
            with self.subTest(value=value):
                coordinator = self.coordinator(device_type=DEVICE_TYPE_K10PRO)
                coordinator.async_send_action = AsyncMock(return_value={"statusCode": value})
                with self.assertLogs(module._LOGGER, level="WARNING") as logs:
                    await coordinator.async_refresh_k10_rooms()
                self.assertEqual(logs.records[0].getMessage(),
                                 "GetCleanPolicyList failed (statusCode unknown)")

    async def test_missing_property_status_is_safe(self):
        coordinator = self.coordinator()
        with cloud_response({}), self.assertRaises(module.UpdateFailed) as error:
            await coordinator.async_get_properties([1004])
        self.assertEqual(str(error.exception), "Property fetch failed (resultCode unknown)")

    async def test_missing_device_status_is_safe(self):
        coordinator = self.coordinator()
        with cloud_response({}), self.assertRaises(module.UpdateFailed) as error:
            await coordinator.async_get_k10_status()
        self.assertEqual(str(error.exception), "K10+ getstatus failed (statusCode unknown)")

    async def test_missing_schedule_status_is_safe(self):
        coordinator = self.coordinator(device_type=DEVICE_TYPE_K10PRO)
        coordinator.async_send_action = AsyncMock(return_value={})
        with self.assertLogs(module._LOGGER, level="WARNING") as logs:
            await coordinator.async_refresh_k10_rooms()
        self.assertEqual(logs.records[0].getMessage(),
                         "GetCleanPolicyList failed (statusCode unknown)")

    async def test_successful_property_response_is_unchanged(self):
        coordinator = self.coordinator()
        with cloud_response({"resultCode": 100, "data": {"1004": {"value": 85}}}):
            properties = await coordinator.async_get_properties([1004])
        self.assertEqual(properties, {1004: 85})

    async def test_successful_status_response_is_unchanged(self):
        coordinator = self.coordinator()
        with cloud_response({"statusCode": 100, "body": {"items": [{"WorkingStatus": 7}]}}):
            status = await coordinator.async_get_k10_status()
        self.assertEqual(status, {"WorkingStatus": 7})

    async def test_successful_schedule_response_is_unchanged(self):
        coordinator = self.coordinator(device_type=DEVICE_TYPE_K10PRO)
        coordinator.async_send_action = AsyncMock(return_value={
            "statusCode": 100,
            "body": {"result": json.dumps({"CleanPolicyList": json.dumps({
                "value": [{"smartAreaIds": [1, 4]}],
            })})},
        })
        await coordinator.async_refresh_k10_rooms()
        self.assertEqual(coordinator._rooms, {"room1": "room1", "room4": "room4"})


if __name__ == "__main__":
    unittest.main()
