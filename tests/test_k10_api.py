"""Run with python3 -m unittest discover -s tests -p test_k10_api.py.

No HA installation, user credentials, network, or physical robot is used.
"""

import base64
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

PATH = Path(__file__).resolve().parents[1] / "custom_components/switchbot_vacuum/k10_api.py"
SPEC = importlib.util.spec_from_file_location("k10_api", PATH)
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)


def room(*, room_id, name, passes=2, suction="max"):
    return {
        "id": room_id,
        "name": base64.b64encode(name.encode()).decode(),
        "cleanTimes": passes,
        "windMode": suction,
        "vertexs": [[0, 0], [0, 100], [100, 0]],
    }


def map_data(*, rooms, map_id=101):
    return {
        "mapId": map_id,
        "cleanId": "example-clean",
        "smartArea": {
            "mapId": map_id,
            "value": rooms,
            "activeIds": [],
            "cleanTimes": 2,
            "areaCleanActiveId": [],
            "autoOrder": False,
            "isAttrOn": 1,
        },
    }


def storage(*, endpoint="oss-eu-central-1.aliyuncs.com"):
    return {
        "provider": "aliyun",
        "bucket": "eu1-ali-1days",
        "endpoint": endpoint,
        "path": "example/room.txt",
        "sts": {
            "accesskey_id": "fake-key",
            "accesskey_secret": "fake-secret",
            "security_token": "fake-sts",
        },
    }


class ProtocolTests(unittest.TestCase):
    def test_known_signature(self):
        result = api.signed_params("installation", timestamp=1700000000, nonce="abc")
        self.assertEqual(result["sign"], "63c640785a2c4005955e497796b5184a")

    def test_decodes_room_name_from_map(self):
        data = map_data(rooms=[room(room_id=1, name="Entry")])
        self.assertEqual(api.room_names(data), {"1": "Entry"})

    def test_selects_only_requested_room(self):
        data = map_data(rooms=[room(room_id=1, name="Entry"), room(room_id=4, name="Kitchen")])
        result = api.prepare_rooms(data, ["Entry"], 1, True)
        self.assertEqual(result["activeIds"], [1])

    def test_applies_requested_passes_to_selected_room(self):
        data = map_data(rooms=[room(room_id=1, name="Entry", passes=2)])
        result = api.prepare_rooms(data, ["Entry"], 1, True)
        self.assertEqual(result["value"][0]["cleanTimes"], 1)

    def test_preserves_suction(self):
        data = map_data(rooms=[room(room_id=1, name="Entry", suction="max")])
        result = api.prepare_rooms(data, ["Entry"], 1, True)
        self.assertEqual(result["value"][0]["windMode"], "max")

    def test_unknown_room_does_not_fall_back_to_full_house(self):
        data = map_data(rooms=[room(room_id=1, name="Entry")])
        with self.assertRaises(api.K10ProtocolError):
            api.prepare_rooms(data, ["Unknown"], 1, True)

    def test_rejects_mismatched_map(self):
        data = map_data(rooms=[room(room_id=1, name="Entry")], map_id=101)
        data["smartArea"]["mapId"] = 102
        with self.assertRaises(api.K10ProtocolError):
            api.prepare_rooms(data, ["Entry"], 1, True)

    def test_rejects_upload_credentials_for_other_host(self):
        info = storage(endpoint="attacker.example")
        with self.assertRaises(api.K10ProtocolError):
            api.oss_request(info, b"{}")


class Response:
    def __init__(self, *, data=None, status=200):
        self.data, self.status = data, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def json(self):
        return self.data


class Session:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return Response(data=next(self.replies))

    def put(self, url, **kwargs):
        self.calls.append(("PUT", url, kwargs))
        return Response()


class AsyncProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_transport_timeout_does_not_retry_start(self):
        data = map_data(rooms=[room(room_id=1, name="Entry")])
        client = api.K10Api("example-device", "example-product", "installation")
        client.token = "fake-token"
        client.get_properties = AsyncMock(return_value={
            "MopModeSwitching": 0, "MoppingPadInstalled": False, "WorkingStatus": 7
        })
        client.get_map = AsyncMock(
            return_value=(data, {"MapID": "101", "CleanID": "example-clean"})
        )

        class TimeoutSession(Session):
            def request(self, method, url, **kwargs):
                if method == "POST":
                    self.calls.append((method, url, kwargs))
                    raise TimeoutError("simulated ambiguous start")
                return super().request(method, url, **kwargs)

        session = TimeoutSession([{"code": 0, "data": {"upload_info": storage()}}])
        with self.assertRaises(TimeoutError):
            await client.clean_rooms(session, ["Entry"])
        self.assertEqual(sum(c[0] == "POST" for c in session.calls), 1)

    async def test_map_host_is_checked_before_download(self):
        client = api.K10Api("example-device", "example-product", "installation")
        client.request = AsyncMock(
            return_value={
                "code": 0,
                "data": {
                    "result": json.dumps({"MapPkgOssInfo": json.dumps({"Url": "map-object"})}),
                    "extend": {"s3_signs": {"map-object": "https://attacker.example/map"}},
                },
            }
        )
        with self.assertRaises(api.K10ProtocolError):
            await client.get_map(Session([]))

    async def test_service_map_id_is_integer(self):
        data = map_data(rooms=[room(room_id=1, name="Entry")], map_id=11303)
        client = api.K10Api("example-device", "example-product", "installation")
        client.token = "fake-token"
        client.get_properties = AsyncMock(return_value={
            "MopModeSwitching": 0, "MoppingPadInstalled": False, "WorkingStatus": 7
        })
        client.get_map = AsyncMock(
            return_value=(data, {"MapID": "11303", "CleanID": "example-clean"})
        )
        session = Session(
            [
                {"code": 0, "data": {"upload_info": storage()}},
                {"code": 0, "data": {"request_id": "example-request"}},
                {"code": 0, "data": {"result": '{"ErrorNO":0}'}},
            ]
        )
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            await client.clean_rooms(session, ["Entry"])
        start = next(c for c in session.calls if c[0] == "POST")
        self.assertEqual(json.loads(start[2]["data"]["input"])["MapID"], 11303)

    async def test_start_is_sent_once_while_reply_is_pending(self):
        data = map_data(rooms=[room(room_id=1, name="Entry")])
        client = api.K10Api("example-device", "example-product", "installation")
        client.token = "fake-token"
        client.get_properties = AsyncMock(return_value={
            "MopModeSwitching": 0, "MoppingPadInstalled": False, "WorkingStatus": 7
        })
        client.get_map = AsyncMock(
            return_value=(data, {"MapID": "101", "CleanID": "example-clean"})
        )
        session = Session(
            [
                {"code": 0, "data": {"upload_info": storage()}},
                {"code": 0, "data": {"request_id": "example-request"}},
                {"code": 202016, "data": {"errno": 1306050}},
                {"code": 0, "data": {"result": '{"ErrorNO":0}'}},
            ]
        )
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            await client.clean_rooms(session, ["Entry"])
        self.assertEqual(sum(c[0] == "POST" for c in session.calls), 1)

    async def test_robot_error_is_not_reported_as_success(self):
        data = map_data(rooms=[room(room_id=1, name="Entry")])
        client = api.K10Api("example-device", "example-product", "installation")
        client.token = "fake-token"
        client.get_properties = AsyncMock(return_value={
            "MopModeSwitching": 0, "MoppingPadInstalled": False, "WorkingStatus": 7
        })
        client.get_map = AsyncMock(
            return_value=(data, {"MapID": "101", "CleanID": "example-clean"})
        )
        session = Session(
            [
                {"code": 0, "data": {"upload_info": storage()}},
                {"code": 0, "data": {"request_id": "example-request"}},
                {"code": 0, "data": {"result": '{"ErrorNO":5}'}},
            ]
        )
        with (
            patch.object(api.asyncio, "sleep", new=AsyncMock()),
            self.assertRaises(api.K10ProtocolError),
        ):
            await client.clean_rooms(session, ["Entry"])

    async def test_unknown_room_never_uploads_or_starts(self):
        data = map_data(rooms=[room(room_id=1, name="Entry")])
        client = api.K10Api("example-device", "example-product", "installation")
        client.get_map = AsyncMock(
            return_value=(data, {"MapID": "101", "CleanID": "example-clean"})
        )
        session = Session([])
        with self.assertRaises(api.K10ProtocolError):
            await client.clean_rooms(session, ["Unknown"])
        self.assertEqual(session.calls, [])


class ControlTests(unittest.IsolatedAsyncioTestCase):
    def client(self):
        client = api.K10Api("example-device", "example-product", "installation")
        client.token = "fake-token"
        return client

    async def test_empty_dustbin_sends_exact_app_service(self):
        client = self.client()
        client.get_properties = AsyncMock(return_value={"WorkingStatus": 7})
        session = Session([
            {"code": 0, "data": {"request_id": "empty-request"}},
            {"code": 0, "data": {"result": '{"ErrorNO":0}'}},
        ])
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            await client.empty_dustbin(session)
        form = next(c for c in session.calls if c[0] == "POST")[2]["data"]
        self.assertEqual(form, {"product_key": "example-product", "device_name": "example-device",
                                "identifier": "StartCollectingDust", "input": "{}"})

    async def test_empty_dustbin_requires_dock(self):
        for state in (0, 1, 2, 3, 4, 5, 11, None):
            with self.subTest(state=state):
                client = self.client()
                client.get_properties = AsyncMock(return_value={"WorkingStatus": state})
                session = Session([])
                with self.assertRaises(api.K10ProtocolError):
                    await client.empty_dustbin(session)
                self.assertEqual(session.calls, [])

    async def test_empty_dustbin_rejection_is_not_success(self):
        client = self.client()
        client.get_properties = AsyncMock(return_value={"WorkingStatus": 6})
        session = Session([
            {"code": 0, "data": {"request_id": "empty-request"}},
            {"code": 0, "data": {"result": '{"ErrorNO":5}'}},
        ])
        with (
            patch.object(api.asyncio, "sleep", new=AsyncMock()),
            self.assertRaises(api.K10ProtocolError),
        ):
            await client.empty_dustbin(session)

    async def test_mode_uses_exact_values_and_property_form(self):
        for mode, value, installed, previous in (("sweep", 0, False, 2), ("mop", 2, True, 0)):
            with self.subTest(mode=mode):
                client = self.client()
                client.get_properties = AsyncMock(side_effect=[
                    {"MopModeSwitching": previous, "MoppingPadInstalled": installed,
                     "WorkingStatus": 7},
                    {"MopModeSwitching": value, "MoppingPadInstalled": installed},
                ])
                session = Session([{"code": 0}])
                await client.set_mode(session, mode)
                self.assertEqual([(c[1], c[2]["data"]) for c in session.calls], [
                    (api.API+"/v1/iot/device/set_property", {
                        "product_key": "example-product", "device_name": "example-device",
                        "items": json.dumps({"MopModeSwitching": value}, separators=(",", ":"))})
                ])

    async def test_mode_requires_correct_pad_state(self):
        for mode, installed in (("mop", False), ("sweep", True), ("mop", None), ("sweep", None)):
            with self.subTest(mode=mode, installed=installed):
                client = self.client()
                client.get_properties = AsyncMock(return_value={"MoppingPadInstalled": installed})
                session = Session([])
                with self.assertRaises(api.K10ProtocolError):
                    await client.set_mode(session, mode)
                self.assertEqual(session.calls, [])

    async def test_combined_mode_is_rejected(self):
        client = self.client()
        client.get_properties = AsyncMock(return_value={"MoppingPadInstalled": True})
        session = Session([])
        with self.assertRaises(api.K10ProtocolError):
            await client.set_mode(session, "sweep_mop")
        self.assertEqual(session.calls, [])

    async def test_mode_change_cannot_stop_a_running_task(self):
        client = self.client()
        client.get_properties = AsyncMock(return_value={
            "MopModeSwitching": 0, "MoppingPadInstalled": True, "WorkingStatus": 2
        })
        session = Session([])
        with self.assertRaises(api.K10ProtocolError):
            await client.set_mode(session, "mop")
        self.assertEqual(session.calls, [])

    async def test_unconfirmed_mode_does_not_start_cleaning(self):
        client = self.client()
        client.get_properties = AsyncMock(return_value={
            "MopModeSwitching": 0, "MoppingPadInstalled": True, "WorkingStatus": 7
        })
        client.get_map = AsyncMock(return_value=(
            map_data(rooms=[room(room_id=1, name="Entry")]),
            {"MapID": "101", "CleanID": "example-clean"}
        ))
        session = Session([{"code": 0}])
        with (
            patch.object(api.asyncio, "sleep", new=AsyncMock()),
            self.assertRaises(api.K10ProtocolError),
        ):
            await client.clean_rooms(session, ["Entry"], mode="mop")
        self.assertEqual([c[1] for c in session.calls], [api.API+"/v1/iot/device/set_property"])

    async def test_room_suction_matches_each_app_setting(self):
        for level, expected in ((1, "quiet"), (2, "auto"), (3, "strong"), (4, "max")):
            with self.subTest(level=level):
                data = map_data(rooms=[room(room_id=1, name="Entry", suction="max"),
                                       room(room_id=4, name="Kitchen", suction="strong")])
                payload = api.prepare_rooms(data, ["Entry"], 1, True, fan_level=level)
                self.assertEqual([r["windMode"] for r in payload["value"]], [expected, "strong"])

    async def test_room_suction_does_not_change_original_map(self):
        data = map_data(rooms=[room(room_id=1, name="Entry", suction="max")])
        api.prepare_rooms(data, ["Entry"], 1, True, fan_level=1)
        self.assertEqual(data["smartArea"]["value"][0]["windMode"], "max")

    async def test_explicit_room_suction_enables_room_settings(self):
        data = map_data(rooms=[room(room_id=1, name="Entry")])
        data["smartArea"]["isAttrOn"] = 0
        payload = api.prepare_rooms(data, ["Entry"], 1, True, fan_level=2)
        self.assertEqual(payload["isAttrOn"], 1)

    async def test_invalid_room_suction_rejected_before_upload(self):
        data = map_data(rooms=[room(room_id=1, name="Entry")])
        with self.assertRaises(api.K10ProtocolError):
            api.prepare_rooms(data, ["Entry"], 1, True, fan_level=5)

    async def test_global_suction_uses_zero_based_property_values(self):
        for level in (0, 1, 2, 3):
            with self.subTest(level=level):
                client = self.client()
                session = Session([{"code": 0}])
                await client.set_suction(session, level)
                self.assertEqual(json.loads(session.calls[0][2]["data"]["items"]),
                                 {"SuctionPowLevel": level})

    async def test_rejected_property_write_is_not_success(self):
        client = self.client()
        with self.assertRaises(api.K10ProtocolError):
            await client.set_suction(Session([{"code": 123}]), 0)

    async def test_room_upload_contains_requested_suction(self):
        client = self.client()
        client.get_map = AsyncMock(return_value=(
            map_data(rooms=[room(room_id=1, name="Entry", suction="max")]),
            {"MapID": "101", "CleanID": "example-clean"}
        ))
        client.get_properties = AsyncMock(return_value={
            "MopModeSwitching": 0, "MoppingPadInstalled": False, "WorkingStatus": 7
        })
        session = Session([
            {"code": 0, "data": {"upload_info": storage()}},
            {"code": 0, "data": {"request_id": "room-request"}},
            {"code": 0, "data": {"result": '{"ErrorNO":0}'}},
        ])
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            await client.clean_rooms(session, ["Entry"], mode="sweep", fan_level=2)
        uploaded = json.loads(next(c[2]["data"] for c in session.calls if c[0] == "PUT"))
        self.assertEqual(uploaded["value"][0]["windMode"], "auto")

    async def test_mop_mode_confirmed_before_room_start(self):
        client = self.client()
        client.get_map = AsyncMock(return_value=(
            map_data(rooms=[room(room_id=1, name="Entry")]),
            {"MapID": "101", "CleanID": "example-clean"}
        ))
        client.get_properties = AsyncMock(side_effect=[
            {"MopModeSwitching": 0, "MoppingPadInstalled": True, "WorkingStatus": 7},
            {"MopModeSwitching": 2, "MoppingPadInstalled": True, "WorkingStatus": 7},
        ])
        session = Session([
            {"code": 0},
            {"code": 0, "data": {"upload_info": storage()}},
            {"code": 0, "data": {"request_id": "room-request"}},
            {"code": 0, "data": {"result": '{"ErrorNO":0}'}},
        ])
        with patch.object(api.asyncio, "sleep", new=AsyncMock()):
            await client.clean_rooms(session, ["Entry"], mode="mop")
        self.assertEqual([c[1].removeprefix(api.API) for c in session.calls if c[0] == "POST"],
                         ["/v1/iot/device/set_property", "/v1/iot/device/invoke_service_async"])

    async def test_missing_mode_cannot_start_a_room(self):
        client = self.client()
        client.get_map = AsyncMock(return_value=(
            map_data(rooms=[room(room_id=1, name="Entry")]),
            {"MapID": "101", "CleanID": "example-clean"}
        ))
        client.get_properties = AsyncMock(return_value={"MoppingPadInstalled": False})
        session = Session([])
        with self.assertRaises(api.K10ProtocolError):
            await client.clean_rooms(session, ["Entry"])
        self.assertEqual(session.calls, [])


if __name__ == "__main__":
    unittest.main()
