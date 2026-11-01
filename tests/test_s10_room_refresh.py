"""S10 room refresh regressions with synthetic HTTP, SDK and registry data."""
from __future__ import annotations

import asyncio
import io
import json
import logging
import threading
import time
import zipfile
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiobotocore.session
import pytest

from custom_components.switchbot_vacuum import coordinator as module
from custom_components.switchbot_vacuum import sensor as sensor_platform
from custom_components.switchbot_vacuum.const import (
    CONF_DEVICE_MAC,
    DEVICE_TYPE_S10,
    DOMAIN,
    PROP_MAP_INFO,
    PROP_ROOM_PLANS,
    PROP_S3_BUCKET,
)

ROOMS = {"ROOM_TEST_1": "Test room"}


@pytest.fixture
def coordinator():
    """Avoid HA startup/networking while exercising the actual coordinator methods."""
    coord = object.__new__(module.SwitchBotS10Coordinator)
    coord.hass = MagicMock()
    coord.entry = SimpleNamespace(
        data={CONF_DEVICE_MAC: "AABBCCDDEEFF", "device_type": DEVICE_TYPE_S10},
        options={"keep_option": True}, entry_id="test-entry",
    )
    coord.device_mac = "AABBCCDDEEFF"
    coord.wonderlab_endpoint = "https://example.invalid"
    coord.access_token = "fake-account-token"
    coord._uuid = "test-installation"
    coord._ensure_token = AsyncMock()
    coord._rooms = dict(ROOMS)
    coord._last_room_refresh = 0
    coord._last_room_attempt = None
    return coord


def policy_payload(expiration=None):
    return {"resultCode": 100, "data": {
        "AccessKeyId": "fake-access", "SecretAccessKey": "fake-secret",
        "SessionToken": "fake-session", "awsRegion": "us-west-2",
        "Expiration": expiration or (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }}


def policy_session(payload, status=200):
    response = MagicMock(status=status)
    response.json = AsyncMock(return_value=payload)
    request = AsyncMock()
    request.__aenter__.return_value = response
    session = MagicMock()
    session.post.return_value = request
    return session


async def test_policy_renews_credentials_using_the_app_read_endpoint(coordinator):
    session = policy_session(policy_payload())
    with patch.object(module, "async_get_clientsession", return_value=session):
        creds, region = await coordinator.async_get_map_policy()
    coordinator._ensure_token.assert_awaited_once()
    assert creds == {"accessKeyId": "fake-access", "secretAccessKey": "fake-secret",
                     "sessionToken": "fake-session"}
    assert region == "us-west-2"
    args, kwargs = session.post.call_args
    assert args == ("https://example.invalid/sweeper/v1/task/getPolicy",)
    assert kwargs["json"] == {"deviceID": coordinator.device_mac}
    assert kwargs["allow_redirects"] is False


@pytest.mark.parametrize("expiration", [0, True, "bad-date", "2099-01-01T00:00:00",
                                         float("nan"), float("inf")])
async def test_invalid_or_expired_policy_is_rejected(coordinator, expiration):
    payload = policy_payload()
    payload["data"]["Expiration"] = expiration
    with patch.object(module, "async_get_clientsession",
                      return_value=policy_session(payload)), pytest.raises(module.UpdateFailed):
        await coordinator.async_get_map_policy()


async def test_numeric_expiration_and_default_region(coordinator):
    payload = policy_payload(time.time() + 3600)
    payload["data"].pop("awsRegion")
    with patch.object(module, "async_get_clientsession",
                      return_value=policy_session(payload)):
        _, region = await coordinator.async_get_map_policy()
    assert region == module.S3_REGION


@pytest.mark.parametrize("payload,status", [
    ({"resultCode": "fake-private-value", "message": "fake-private-value"}, 200),
    ({"resultCode": 100, "data": {"AccessKeyId": "fake-private-value"}}, 200),
    ({"message": "fake-private-value"}, 503),
])
async def test_policy_errors_do_not_expose_response_or_credentials(coordinator, payload, status):
    with patch.object(module, "async_get_clientsession",
                      return_value=policy_session(payload, status)), pytest.raises(module.UpdateFailed) as error:
        await coordinator.async_get_map_policy()
    assert "fake-private" not in str(error.value)


def map_archive(*, missing_labels=False):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("other.json" if missing_labels else "labels.json", json.dumps({
            "data": [{"id": "ROOM_TEST_1", "name": "Test room"}, {"id": "CHARGE_TEST"}],
        }))
    return output.getvalue()


@pytest.mark.parametrize("failure", [None, "read", "zip", "missing_labels"])
async def test_worker_isolates_sdk_loop_and_closes_resources(failure):
    main_thread = threading.get_ident()
    main_loop = asyncio.get_running_loop()
    events = []

    def assert_worker():
        assert threading.get_ident() != main_thread
        assert asyncio.get_running_loop() is not main_loop

    class Body:
        async def __aenter__(self):
            assert_worker()
            return self

        async def __aexit__(self, *_):
            events.append("body closed")

        async def read(self):
            assert_worker()
            if failure == "read":
                raise OSError("fake-private-signed-url")
            return b"invalid zip" if failure == "zip" else map_archive(
                missing_labels=failure == "missing_labels"
            )

    class Client:
        async def __aenter__(self):
            assert_worker()
            return self

        async def __aexit__(self, *_):
            events.append("client closed")

        async def get_object(self, **kwargs):
            assert_worker()
            assert kwargs == {"Bucket": "test-bucket", "Key": "map.zip"}
            return {"Body": Body()}

    class Session:
        def create_client(self, service, **kwargs):
            assert_worker()
            assert service == "s3"
            assert kwargs["region_name"] == "us-west-2"
            assert kwargs["config"].read_timeout == 30
            return Client()

    def get_session():
        assert_worker()
        return Session()

    creds = {"accessKeyId": "fake-access", "secretAccessKey": "fake-secret",
             "sessionToken": "fake-session"}
    with patch.object(aiobotocore.session, "get_session", side_effect=get_session):
        if failure in ("read", "zip"):
            with pytest.raises(OSError if failure == "read" else zipfile.BadZipFile):
                await asyncio.to_thread(module._download_map_rooms, creds,
                                        "test-bucket", "map.zip", "us-west-2")
        else:
            rooms = await asyncio.to_thread(module._download_map_rooms, creds,
                                           "test-bucket", "map.zip", "us-west-2")
            assert rooms == (None if failure == "missing_labels" else ROOMS)
    assert events == ["body closed", "client closed"]


@pytest.mark.parametrize("outcome", ["success", "failure", "missing_labels"])
async def test_refresh_uses_executor_and_preserves_cache_on_failure(coordinator, outcome, caplog):
    coordinator.async_get_properties = AsyncMock(return_value={
        PROP_MAP_INFO: {"resource": "map.zip"}, PROP_S3_BUCKET: "test-bucket",
    })
    coordinator.async_get_map_policy = AsyncMock(return_value=({}, "us-west-2"))
    coordinator.hass.async_add_executor_job = AsyncMock(
        side_effect=OSError("fake-private-signed-url") if outcome == "failure" else None,
        return_value=None if outcome == "missing_labels" else {"ROOM_TEST_2": "New test room"},
    )
    with caplog.at_level(logging.WARNING):
        await coordinator.async_refresh_rooms()
    coordinator.async_get_properties.assert_awaited_once_with(
        [PROP_MAP_INFO, PROP_S3_BUCKET, PROP_ROOM_PLANS]
    )
    assert coordinator.hass.async_add_executor_job.call_args.args[0] is module._download_map_rooms
    assert "fake-private" not in caplog.text
    if outcome != "success":
        assert coordinator._rooms == ROOMS
        coordinator.hass.config_entries.async_update_entry.assert_not_called()
    else:
        assert coordinator._rooms == {"ROOM_TEST_2": "New test room"}
        options = coordinator.hass.config_entries.async_update_entry.call_args.kwargs["options"]
        assert options == {"keep_option": True, "cached_rooms": coordinator._rooms}


def test_cache_restore_is_per_entry_and_accepts_an_explicit_empty_cache(coordinator):
    coordinator.entry.options = {"cached_rooms": {"ROOM_TEST_1": "Test room", 7: "bad"}}
    assert module._restore_rooms(coordinator.hass, coordinator.entry) == ROOMS
    coordinator.entry.options = {"cached_rooms": {}}
    with patch.object(module.er, "async_get") as registry:
        assert module._restore_rooms(coordinator.hass, coordinator.entry) == {}
    registry.assert_not_called()
    assert module._restore_rooms(coordinator.hass, None) == {}


def test_registry_migration_uses_only_this_integrations_device_rooms(coordinator):
    entries = [SimpleNamespace(platform=platform, domain=domain, unique_id=uid,
                               original_name="Test room") for platform, domain, uid in [
        (DOMAIN, "sensor", "AABBCCDDEEFF_room_ROOM_TEST_1"),
        (DOMAIN, "sensor", "OTHERDEVICE_room_ROOM_TEST_2"),
        (DOMAIN, "sensor", "AABBCCDDEEFF_battery"),
        ("other_integration", "sensor", "AABBCCDDEEFF_room_ROOM_TEST_3"),
    ]]
    with patch.object(module.er, "async_get") as registry, patch.object(
        module.er, "async_entries_for_config_entry", return_value=entries
    ) as entries_for_entry:
        assert module._restore_rooms(coordinator.hass, coordinator.entry) == ROOMS
    entries_for_entry.assert_called_once_with(registry.return_value, coordinator.entry.entry_id)


def test_cache_persistence_preserves_options_and_skips_unchanged_writes(coordinator):
    def update(entry, **kwargs):
        entry.options = kwargs["options"]
    coordinator.hass.config_entries.async_update_entry.side_effect = update
    coordinator._persist_rooms()
    coordinator._persist_rooms()
    coordinator.hass.config_entries.async_update_entry.assert_called_once()
    assert coordinator.entry.options == {"keep_option": True, "cached_rooms": ROOMS}


async def test_failed_background_refresh_is_throttled_even_at_monotonic_zero(coordinator):
    coordinator.async_refresh_rooms = AsyncMock()
    coordinator.data = {"rooms": ROOMS}
    coordinator.async_set_updated_data = MagicMock()
    with patch.object(module.time, "monotonic", side_effect=[0, 1, 299, 300]):
        for _ in range(4):
            await coordinator._background_room_refresh()
    assert coordinator.async_refresh_rooms.await_count == 2


async def test_room_listener_is_removed_on_entry_unload():
    coord = MagicMock()
    coord.data = {"rooms": ROOMS}
    coord.device_mac = "AABBCCDDEEFF"
    entry = SimpleNamespace(entry_id="test-entry", data={"device_type": DEVICE_TYPE_S10},
                            async_on_unload=MagicMock())
    hass = MagicMock()
    hass.data = {DOMAIN: {entry.entry_id: coord}}
    await sensor_platform.async_setup_entry(hass, entry, MagicMock())
    unsubscribe = coord.async_add_listener.return_value
    entry.async_on_unload.assert_called_once_with(unsubscribe)
    entry.async_on_unload.call_args.args[0]()
    unsubscribe.assert_called_once()
