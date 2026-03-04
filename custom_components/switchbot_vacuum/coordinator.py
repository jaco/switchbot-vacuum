"""Data update coordinator for SwitchBot Vacuum."""
from __future__ import annotations

import io
import json
import logging
import time
import uuid
import zipfile
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_AUTH_HOST,
    API_HOST_EU,
    API_TIMEOUT,
    APP_VERSION,
    CLIENT_ID,
    CONF_DEVICE_MAC,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEVICE_TYPE_S10,
    DOMAIN,
    PROP_AWS_CREDS,
    PROP_BATTERY,
    PROP_CLEAN_MODE,
    PROP_CLEAN_SUMMARY,
    PROP_ERROR_CODE,
    PROP_FIRMWARE,
    PROP_MAP_INFO,
    PROP_ONLINE,
    PROP_ROOM_PLANS,
    PROP_S3_BUCKET,
    PROP_WORK_STATUS,
    S3_REGION,
    TOKEN_REFRESH_SECONDS,
    UPDATE_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

STATUS_PROPS = [PROP_ONLINE, PROP_BATTERY, PROP_WORK_STATUS, PROP_ERROR_CODE,
                PROP_CLEAN_MODE, PROP_CLEAN_SUMMARY, PROP_FIRMWARE]


class SwitchBotS10Coordinator(DataUpdateCoordinator):
    """Manage fetching data from SwitchBot Vacuum API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.access_token: str | None = None
        self.device_mac: str | None = None
        self.device_name: str | None = None
        self.user_id: str | None = None
        self._uuid: str = str(uuid.uuid4())
        self._token_expiry: float = 0
        self._rooms: dict[str, str] = {}  # ROOM_ID -> name
        self._last_room_refresh: float = 0

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )

    def _headers(self, auth: str | None = None) -> dict[str, str]:
        """Build common request headers."""
        return {
            "authorization": auth if auth is not None else (self.access_token or ""),
            "uuid": self._uuid,
            "requestid": str(uuid.uuid4()),
            "appversion": APP_VERSION,
            "content-type": "application/json; charset=UTF-8",
        }

    async def async_login(self) -> None:
        """Authenticate with SwitchBot API."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_AUTH_HOST}/account/api/v1/user/login",
                headers=self._headers(auth=""),
                json={
                    "clientId": CLIENT_ID,
                    "deviceInfo": {
                        "deviceId": self._uuid,
                        "deviceName": "Home Assistant",
                        "model": "Home Assistant",
                    },
                    "grantType": "password",
                    "password": self.entry.data[CONF_PASSWORD],
                    "username": self.entry.data[CONF_USERNAME],
                    "verifyCode": "",
                },
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
            ) as resp:
                data = await resp.json()
                body = data.get("body", {})
                token = body.get("access_token")
                if not token:
                    raise ConfigEntryAuthFailed(
                        f"Login failed: {data.get('message', data.get('statusCode', 'unknown'))}"
                    )
                self.access_token = token
                self._token_expiry = time.time() + TOKEN_REFRESH_SECONDS

    async def async_discover_devices(self) -> list[dict[str, Any]]:
        """Find all S10 devices in the account."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_HOST_EU}/wonder/device/v3/getdevice",
                headers=self._headers(),
                json={"required_type": "All"},
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
            ) as resp:
                data = await resp.json()
                devices = []
                for device in data.get("body", {}).get("Items", []):
                    if device.get("device_detail", {}).get("device_type") == DEVICE_TYPE_S10:
                        devices.append({
                            "device_mac": device["device_mac"],
                            "device_name": device.get("device_name", "SwitchBot Vacuum"),
                            "user_id": device.get("userID"),
                            "group_id": device.get("groupID"),
                        })
                return devices

    def set_device(self, device_mac: str, device_name: str, user_id: str | None = None) -> None:
        """Set the target device after config flow discovery."""
        self.device_mac = device_mac
        self.device_name = device_name
        self.user_id = user_id

    async def async_get_properties(self, property_ids: list[int]) -> dict[int, Any]:
        """Fetch device properties from shadow API."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_HOST_EU}/device/device/v1/shadow/getByIDs",
                headers=self._headers(),
                json={"deviceID": self.device_mac, "propertyIDs": property_ids},
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
            ) as resp:
                data = await resp.json()
                if data.get("resultCode") != 100:
                    raise UpdateFailed(f"Property fetch failed: {data}")
                result = {}
                for pid_str, prop in (data.get("data") or {}).items():
                    result[int(pid_str)] = prop.get("value")
                return result

    async def async_send_command(
        self, function_id: int, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a command to the device via invokeFunc."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_HOST_EU}/command/cmd/api/v1/func/invoke",
                headers=self._headers(),
                json={
                    "deviceID": self.device_mac,
                    "functionID": function_id,
                    "params": params,
                    "notify": {
                        "type": "mqtt",
                        "url": f"v1_1/{self._uuid}/APP_HA_{self._uuid}/funcResp",
                    },
                    "optSrc": "app",
                    "timeout": 65535,
                },
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
            ) as resp:
                return await resp.json()

    def _extract_rooms_from_room_plans(self, room_plans: Any) -> dict[str, str]:
        """Try to extract room names from PROP_ROOM_PLANS property."""
        rooms: dict[str, str] = {}
        if not room_plans:
            return rooms
        plans = room_plans if isinstance(room_plans, list) else []
        if isinstance(room_plans, dict):
            plans = room_plans.get("data", room_plans.get("rooms", []))
        for room in plans:
            if not isinstance(room, dict):
                continue
            room_id = str(room.get("id", room.get("roomId", "")))
            name = room.get("name", room.get("roomName", room_id))
            if room_id.startswith("ROOM_"):
                rooms[room_id] = name
        return rooms

    async def async_refresh_rooms(self) -> None:
        """Download map from S3 and extract room names."""
        try:
            props = await self.async_get_properties(
                [PROP_MAP_INFO, PROP_AWS_CREDS, PROP_S3_BUCKET, PROP_ROOM_PLANS]
            )
        except UpdateFailed:
            _LOGGER.warning("Failed to fetch map properties for room refresh")
            return

        # Try room plans property first (no S3 needed)
        room_plans = props.get(PROP_ROOM_PLANS)
        rooms_from_plans = self._extract_rooms_from_room_plans(room_plans)
        if rooms_from_plans:
            self._rooms = rooms_from_plans
            self._last_room_refresh = time.time()
            _LOGGER.info("Loaded %d rooms from room plans property", len(rooms_from_plans))
            return

        # Fall back to S3 map download
        creds = props.get(PROP_AWS_CREDS)
        map_info = props.get(PROP_MAP_INFO)
        bucket = props.get(PROP_S3_BUCKET, "prod-eu-sweeper-origin")

        if not creds or not isinstance(creds, dict):
            _LOGGER.warning("No AWS credentials in property %s", PROP_AWS_CREDS)
            return

        if creds.get("expiration", 0) < time.time():
            _LOGGER.debug("AWS credentials expired, skipping S3 map download")
            return

        resource = None
        if isinstance(map_info, dict):
            resource = map_info.get("resource")

        if not resource:
            _LOGGER.warning("No map resource path found")
            return

        try:
            import aiobotocore.session
            boto_session = aiobotocore.session.get_session()
            async with boto_session.create_client(
                "s3",
                region_name=S3_REGION,
                aws_access_key_id=creds["accessKeyId"],
                aws_secret_access_key=creds["secretAccessKey"],
                aws_session_token=creds["sessionToken"],
            ) as s3:
                resp = await s3.get_object(Bucket=bucket, Key=resource)
                zip_bytes = await resp["Body"].read()
        except Exception as exc:
            _LOGGER.warning("Failed to download map from S3: %s", exc)
            return

        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                if "labels.json" in zf.namelist():
                    labels = json.loads(zf.read("labels.json"))
                    rooms = {}
                    for room in labels.get("data", []):
                        room_id = room.get("id", "")
                        name = room.get("name", room_id)
                        if room_id.startswith("ROOM_"):
                            rooms[room_id] = name
                    self._rooms = rooms
                    self._last_room_refresh = time.time()
                    _LOGGER.info("Loaded %d rooms from map", len(rooms))
        except Exception as exc:
            _LOGGER.warning("Failed to parse map zip: %s", exc)

    async def _background_room_refresh(self) -> None:
        """Refresh rooms in the background so it doesn't block coordinator updates."""
        try:
            await self.async_refresh_rooms()
            if self._rooms:
                self.async_set_updated_data(self.data | {"rooms": self._rooms})
        except Exception:
            _LOGGER.debug("Background room refresh failed", exc_info=True)

    @property
    def rooms(self) -> dict[str, str]:
        """Return room ID to name mapping."""
        return self._rooms

    async def _ensure_token(self) -> None:
        """Refresh token if needed."""
        if not self.access_token or time.time() >= self._token_expiry:
            await self.async_login()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch status data from device."""
        await self._ensure_token()

        if not self.device_mac:
            # Load from config entry
            self.device_mac = self.entry.data.get(CONF_DEVICE_MAC)

        props = await self.async_get_properties(STATUS_PROPS)

        # Refresh rooms periodically (non-blocking to avoid setup timeout)
        if time.time() - self._last_room_refresh > 86400:  # 24h
            self.hass.async_create_task(self._background_room_refresh())

        return {
            "online": props.get(PROP_ONLINE, False),
            "battery": props.get(PROP_BATTERY, 0),
            "work_status": props.get(PROP_WORK_STATUS, 1),
            "error_code": props.get(PROP_ERROR_CODE, 0),
            "clean_mode": props.get(PROP_CLEAN_MODE, {}),
            "clean_summary": props.get(PROP_CLEAN_SUMMARY, {}),
            "firmware": props.get(PROP_FIRMWARE, ""),
            "rooms": self._rooms,
        }
