"""Focused checks using Home Assistant's real Python runtime and fake services."""

import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError

from custom_components.switchbot_vacuum import (
    button,
    config_flow,
    vacuum,
)
from custom_components.switchbot_vacuum import (
    coordinator as coordinator_module,
)
from custom_components.switchbot_vacuum import select as select_platform
from custom_components.switchbot_vacuum.const import CMD_CLEAN, DEVICE_TYPE_K10, DEVICE_TYPE_S10


class K10EntityTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_reuses_ha_managed_http_session(self):
        hass = MagicMock()
        coordinator = object.__new__(coordinator_module.SwitchBotS10Coordinator)
        coordinator.hass = hass
        coordinator.device_mac = "FAKEDEVICE"
        coordinator.wonderlab_endpoint = "https://wonderlabs.eu.api.switchbot.net"
        coordinator.access_token = "fake-token"
        coordinator._uuid = "fake-installation"
        response = MagicMock()
        response.json = AsyncMock(
            return_value={"statusCode": 100, "body": {"items": [{"WorkingStatus": 4}]}}
        )
        context = AsyncMock()
        context.__aenter__.return_value = response
        session = MagicMock()
        session.post.return_value = context
        with patch.object(
            coordinator_module, "async_get_clientsession", return_value=session
        ) as get_session:
            await coordinator.async_get_k10_status()
        get_session.assert_called_once_with(hass)

    def coordinator(self):
        coordinator = MagicMock()
        coordinator.entry.data = {"device_type": DEVICE_TYPE_K10}
        coordinator.device_mac = "FAKEDEVICE"
        coordinator.device_name = "Test K10+"
        coordinator.data = {"firmware": "", "work_status": 7, "rooms": {"room1": "Entry"}}
        coordinator.async_clean_k10_rooms = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()
        coordinator.async_send_command = AsyncMock()
        coordinator.async_send_action = AsyncMock()
        return coordinator

    async def test_room_action_routes_to_k10_protocol(self):
        coordinator = self.coordinator()
        entity = vacuum.SwitchBotS10Vacuum(coordinator)
        await entity.async_clean_rooms(["Entry", "Bedroom"], times=2, force_order=False)
        coordinator.async_clean_k10_rooms.assert_awaited_once_with(
            ["Entry", "Bedroom"], 2, False, None, None
        )

    async def test_k10_action_cannot_start_a_whole_house_clean(self):
        coordinator = self.coordinator()
        entity = vacuum.SwitchBotS10Vacuum(coordinator)
        await entity.async_clean_rooms(["Entry"])
        coordinator.async_send_action.assert_not_awaited()

    async def test_k10_rejects_unmapped_options_before_sending(self):
        for options in ({"mode": "sweep_mop"}, {"water_level": 1}):
            with self.subTest(options=options):
                coordinator = self.coordinator()
                entity = vacuum.SwitchBotS10Vacuum(coordinator)
                with self.assertRaises(HomeAssistantError):
                    await entity.async_clean_rooms(["Entry"], **options)
                coordinator.async_clean_k10_rooms.assert_not_awaited()

    async def test_k10_protocol_failure_does_not_start_full_house(self):
        coordinator = self.coordinator()
        coordinator.async_clean_k10_rooms.side_effect = vacuum.K10ProtocolError("Unknown room")
        entity = vacuum.SwitchBotS10Vacuum(coordinator)
        with self.assertRaisesRegex(HomeAssistantError, "Unknown room"):
            await entity.async_clean_rooms(["Missing room"])
        coordinator.async_send_action.assert_not_awaited()

    async def test_s10_defaults_are_preserved(self):
        coordinator = self.coordinator()
        coordinator.entry.data = {"device_type": DEVICE_TYPE_S10}
        coordinator.data["rooms"] = {"ROOM_001": "Kitchen"}
        entity = vacuum.SwitchBotS10Vacuum(coordinator)
        await entity.async_clean_rooms(["Kitchen"])
        mode = {"fan_level": 1, "times": 1, "type": "sweep_mop", "water_level": 1}
        coordinator.async_send_command.assert_awaited_once_with(
            CMD_CLEAN,
            {"0": "clean_rooms", "1": {"force_order": True, "mode": mode,
              "rooms": [{"room_id": "ROOM_001", "mode": mode}]}},
        )

    async def test_s10_explicit_options_are_preserved(self):
        coordinator = self.coordinator()
        coordinator.entry.data = {"device_type": DEVICE_TYPE_S10}
        coordinator.data["rooms"] = {"ROOM_001": "Kitchen", "ROOM_002": "Bedroom"}
        entity = vacuum.SwitchBotS10Vacuum(coordinator)
        await entity.async_clean_rooms(
            ["Kitchen", "ROOM_002"], mode="mop", fan_level=3, water_level=2,
            times=2, force_order=False,
        )
        mode = {"fan_level": 3, "times": 2, "type": "mop", "water_level": 2}
        coordinator.async_send_command.assert_awaited_once_with(
            CMD_CLEAN,
            {"0": "clean_rooms", "1": {"force_order": False, "mode": mode,
              "rooms": [{"room_id": "ROOM_001", "mode": mode},
                        {"room_id": "ROOM_002", "mode": mode}]}},
        )

    async def test_same_public_actions_are_registered(self):
        coordinator = self.coordinator()
        hass = MagicMock()
        hass.data = {"switchbot_vacuum": {"test-entry": coordinator}}
        platform = MagicMock()
        with patch.object(
            vacuum.entity_platform, "async_get_current_platform", return_value=platform
        ):
            await vacuum.async_setup_entry(
                hass, SimpleNamespace(entry_id="test-entry"), MagicMock()
            )
        self.assertEqual(
            [call.args[0] for call in platform.async_register_entity_service.call_args_list],
            ["clean_rooms", "force_refresh"],
        )

    async def test_service_schema_does_not_inject_s10_options(self):
        coordinator = self.coordinator()
        hass = MagicMock()
        hass.data = {"switchbot_vacuum": {"test-entry": coordinator}}
        platform = MagicMock()
        with patch.object(
            vacuum.entity_platform, "async_get_current_platform", return_value=platform
        ):
            await vacuum.async_setup_entry(
                hass, SimpleNamespace(entry_id="test-entry"), MagicMock()
            )
        schema = vacuum.vol.Schema(platform.async_register_entity_service.call_args_list[0].args[1])
        self.assertEqual(schema({"rooms": ["Entry"]}),
                         {"rooms": ["Entry"], "times": 1, "force_order": True})

    async def test_force_refresh_refreshes_rooms_and_status(self):
        coordinator = self.coordinator()
        coordinator.async_refresh_rooms = AsyncMock()
        coordinator.async_refresh = AsyncMock()
        entity = vacuum.SwitchBotS10Vacuum(coordinator)
        await entity.async_force_refresh()
        self.assertEqual(
            [call[0] for call in coordinator.mock_calls],
            ["async_refresh_rooms", "async_refresh"],
        )

    async def test_k10_uses_selected_device_family(self):
        coordinator = object.__new__(coordinator_module.SwitchBotS10Coordinator)
        coordinator.entry = SimpleNamespace(data={"device_type": DEVICE_TYPE_K10})
        coordinator.device_mac = "SECONDDEVICE"
        coordinator._k10_group_id = None
        coordinator._k10_api = None
        coordinator._uuid = "fake-installation"
        coordinator.access_token = "fake-account-token"
        coordinator.wonderlab_endpoint = "https://wonderlabs.eu.api.switchbot.net"
        coordinator._ensure_token = AsyncMock()
        coordinator._get_product_key = AsyncMock(return_value="second-product")
        coordinator.async_discover_devices = AsyncMock(return_value=[
            {"device_mac": "FIRSTDEVICE", "group_id": "first-family"},
            {"device_mac": "SECONDDEVICE", "group_id": "second-family"},
        ])
        session = MagicMock()
        api = MagicMock()
        api.authorize = AsyncMock()
        with patch.object(coordinator_module, "K10Api", return_value=api):
            await coordinator._authorize_k10_api(session)
        api.authorize.assert_awaited_once_with(
            session, coordinator.wonderlab_endpoint, "fake-account-token", "second-family"
        )

    async def test_confirmed_room_start_keeps_cleaning_until_periodic_status(self):
        coordinator = self.coordinator()
        coordinator.data["work_status"] = 7
        coordinator.async_set_updated_data.side_effect = lambda data: setattr(coordinator, "data", data)

        async def stale_cloud_refresh():
            coordinator.data = coordinator.data | {"work_status": 7}

        coordinator.async_request_refresh = AsyncMock(side_effect=stale_cloud_refresh)
        entity = vacuum.SwitchBotS10Vacuum(coordinator)
        await entity.async_clean_rooms(["Entry"], mode="sweep", fan_level=1)
        self.assertEqual(entity.activity.value, "cleaning")

    async def test_room_action_forwards_k10_mode_and_suction(self):
        coordinator = self.coordinator()
        entity = vacuum.SwitchBotS10Vacuum(coordinator)
        await entity.async_clean_rooms(["Entry"], mode="mop", fan_level=2, times=2)
        coordinator.async_clean_k10_rooms.assert_awaited_once_with(
            ["Entry"], 2, True, "mop", 2
        )

    async def test_standard_fan_action_routes_all_four_k10_levels(self):
        for speed, level in (("quiet", 0), ("standard", 1), ("strong", 2), ("max", 3)):
            with self.subTest(speed=speed):
                coordinator = self.coordinator()
                coordinator.async_k10_control = AsyncMock()
                entity = vacuum.SwitchBotS10Vacuum(coordinator)
                await entity.async_set_fan_speed(speed)
                coordinator.async_k10_control.assert_awaited_once_with("suction", level)

    async def test_unknown_fan_speed_does_not_send(self):
        coordinator = self.coordinator()
        coordinator.async_k10_control = AsyncMock()
        entity = vacuum.SwitchBotS10Vacuum(coordinator)
        with self.assertRaises(HomeAssistantError):
            await entity.async_set_fan_speed("invalid")
        coordinator.async_k10_control.assert_not_awaited()

    async def test_k10_attributes_report_actual_mode(self):
        coordinator = self.coordinator()
        coordinator.data["clean_mode"] = {"type": "mop"}
        entity = vacuum.SwitchBotS10Vacuum(coordinator)
        self.assertEqual(entity.extra_state_attributes["clean_type"], "mop")

    async def test_empty_button_routes_to_selected_coordinator(self):
        coordinator = self.coordinator()
        coordinator.async_k10_control = AsyncMock()
        entity = button.SwitchBotEmptyDustbin(coordinator)
        await entity.async_press()
        coordinator.async_k10_control.assert_awaited_once_with("empty_dustbin")

    async def test_empty_button_label(self):
        entity = button.SwitchBotEmptyDustbin(self.coordinator())
        self.assertEqual(entity.name, "Empty dustbin")

    async def test_cleaning_mode_label(self):
        entity = select_platform.SwitchBotCleaningMode(self.coordinator())
        self.assertEqual(entity.name, "Cleaning mode")

    async def test_cleaning_mode_options_match_k10_hardware(self):
        entity = select_platform.SwitchBotCleaningMode(self.coordinator())
        self.assertEqual(entity.options, ["vacuum", "mop"])

    async def test_mode_selection_routes_without_starting(self):
        for option, mode in (("vacuum", "sweep"), ("mop", "mop")):
            with self.subTest(option=option):
                coordinator = self.coordinator()
                coordinator.async_k10_control = AsyncMock()
                entity = select_platform.SwitchBotCleaningMode(coordinator)
                await entity.async_select_option(option)
                coordinator.async_k10_control.assert_awaited_once_with("mode", mode)
                coordinator.async_send_action.assert_not_awaited()

    async def test_mode_reads_coordinator_state(self):
        coordinator = self.coordinator()
        coordinator.data["clean_mode"] = {"type": "sweep"}
        entity = select_platform.SwitchBotCleaningMode(coordinator)
        self.assertEqual(entity.current_option, "vacuum")

    async def test_controls_are_not_added_for_s10(self):
        coordinator = self.coordinator()
        entry = SimpleNamespace(entry_id="test", data={"device_type": DEVICE_TYPE_S10})
        hass = MagicMock()
        hass.data = {"switchbot_vacuum": {"test": coordinator}}
        for platform in (button, select_platform):
            with self.subTest(platform=platform.__name__):
                add = MagicMock()
                await platform.async_setup_entry(hass, entry, add)
                add.assert_not_called()

    async def test_k10_control_network_errors_are_sanitized(self):
        coordinator = object.__new__(coordinator_module.SwitchBotS10Coordinator)
        coordinator.hass = MagicMock()
        coordinator._authorize_k10_api = AsyncMock(side_effect=TimeoutError("private signed URL"))
        coordinator.async_request_refresh = AsyncMock()
        with (
            patch.object(coordinator_module, "async_get_clientsession", return_value=MagicMock()),
            self.assertRaisesRegex(HomeAssistantError, "TimeoutError") as raised,
        ):
            await coordinator.async_k10_control("empty_dustbin")
        self.assertNotIn("private signed URL", str(raised.exception))

    async def test_new_controls_are_added_for_eu_k10(self):
        coordinator = self.coordinator()
        coordinator.wonderlab_endpoint = "https://wonderlabs.eu.api.switchbot.net"
        entry = SimpleNamespace(entry_id="test", data={"device_type": DEVICE_TYPE_K10})
        hass = MagicMock()
        hass.data = {"switchbot_vacuum": {"test": coordinator}}
        for platform in (button, select_platform):
            with self.subTest(platform=platform.__name__):
                add = MagicMock()
                await platform.async_setup_entry(hass, entry, add)
                self.assertEqual(len(add.call_args.args[0]), 1)

    async def test_controls_unavailable_without_properties(self):
        coordinator = self.coordinator()
        coordinator.last_update_success = True
        coordinator.data["k10_controls_available"] = False
        for cls in (button.SwitchBotEmptyDustbin, select_platform.SwitchBotCleaningMode):
            with self.subTest(entity=cls.__name__):
                self.assertFalse(cls(coordinator).available)

    async def test_status_reads_actual_mop_property(self):
        coordinator = object.__new__(coordinator_module.SwitchBotS10Coordinator)
        coordinator.hass = MagicMock()
        coordinator.wonderlab_endpoint = "https://wonderlabs.eu.api.switchbot.net"
        coordinator._last_room_refresh = time.time()
        coordinator._rooms = {}
        coordinator.async_get_k10_status = AsyncMock(return_value={"WorkingStatus": 7})
        api = MagicMock()
        api.get_properties = AsyncMock(return_value={"MopModeSwitching": 2})
        coordinator._authorize_k10_api = AsyncMock(return_value=api)
        with patch.object(coordinator_module, "async_get_clientsession", return_value=MagicMock()):
            data = await coordinator._async_update_data_k10()
        self.assertEqual(data["clean_mode"]["type"], "mop")

    async def test_property_failure_does_not_break_basic_status(self):
        coordinator = object.__new__(coordinator_module.SwitchBotS10Coordinator)
        coordinator.hass = MagicMock()
        coordinator.wonderlab_endpoint = "https://wonderlabs.eu.api.switchbot.net"
        coordinator._last_room_refresh = time.time()
        coordinator._rooms = {}
        coordinator.async_get_k10_status = AsyncMock(return_value={"WorkingStatus": 7})
        coordinator._authorize_k10_api = AsyncMock(side_effect=TimeoutError())
        with patch.object(coordinator_module, "async_get_clientsession", return_value=MagicMock()):
            data = await coordinator._async_update_data_k10()
        self.assertEqual(data["work_status"], 7)


class CredentialFlowTests(unittest.IsolatedAsyncioTestCase):
    def flow(self, *, devices, login_error=None):
        flow = config_flow.SwitchBotS10ConfigFlow()
        flow.hass = MagicMock()
        entry = SimpleNamespace(
            data={"username": "owner@example.test", "password": "old", "device_mac": "FAKEDEVICE"}
        )
        flow._get_reconfigure_entry = MagicMock(return_value=entry)
        flow._get_reauth_entry = MagicMock(return_value=entry)
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_mismatch = MagicMock()
        flow.async_update_reload_and_abort = MagicMock(return_value={"type": "abort"})
        flow.async_show_form = MagicMock(return_value={"type": "form"})
        coordinator = MagicMock()
        coordinator.async_login = AsyncMock(side_effect=login_error)
        coordinator.async_discover_devices = AsyncMock(return_value=devices)
        return flow, entry, coordinator

    async def test_new_entry_uses_existing_email_password_login(self):
        flow, _, coordinator = self.flow(devices=[
            {"device_mac": "FAKEDEVICE", "device_name": "K10+", "device_type": DEVICE_TYPE_K10,
             "product_key": "test-product"}
        ])
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
        with patch.object(config_flow, "SwitchBotS10Coordinator", return_value=coordinator):
            await flow.async_step_user({"username": "owner@example.test", "password": "test-password"})
        self.assertEqual(coordinator.entry.data,
                         {"username": "owner@example.test", "password": "test-password"})
        coordinator.async_login.assert_awaited_once_with()

    async def test_multiple_devices_preserves_selected_product_key(self):
        flow, _, _ = self.flow(devices=[])
        flow._username = "owner@example.test"
        flow._password = "test-password"
        flow._devices = [
            {"device_mac": "FIRSTDEVICE", "device_name": "First", "device_type": DEVICE_TYPE_S10,
             "product_key": "first-product"},
            {"device_mac": "SECONDDEVICE", "device_name": "Second", "device_type": DEVICE_TYPE_K10,
             "product_key": "second-product"},
        ]
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
        await flow.async_step_device({"device_mac": "SECONDDEVICE"})
        self.assertEqual(flow.async_create_entry.call_args.kwargs["data"],
                         {"username": "owner@example.test", "password": "test-password",
                          "device_mac": "SECONDDEVICE", "device_type": DEVICE_TYPE_K10,
                          "product_key": "second-product"})

    async def test_reconfigure_updates_existing_entry(self):
        flow, entry, coordinator = self.flow(devices=[{"device_mac": "FAKEDEVICE"}])
        with patch.object(config_flow, "SwitchBotS10Coordinator", return_value=coordinator):
            await flow.async_step_reconfigure({"password": "updated-test-password"})
        self.assertIs(flow.async_update_reload_and_abort.call_args.args[0], entry)

    async def test_reconfigure_updates_only_password(self):
        flow, _, coordinator = self.flow(devices=[{"device_mac": "FAKEDEVICE"}])
        with patch.object(config_flow, "SwitchBotS10Coordinator", return_value=coordinator):
            await flow.async_step_reconfigure({"password": "updated-test-password"})
        self.assertEqual(
            flow.async_update_reload_and_abort.call_args.kwargs["data_updates"],
            {"password": "updated-test-password"},
        )

    async def test_wrong_device_cannot_replace_existing_entry(self):
        flow, _, coordinator = self.flow(devices=[{"device_mac": "OTHERDEVICE"}])
        with patch.object(config_flow, "SwitchBotS10Coordinator", return_value=coordinator):
            await flow.async_step_reconfigure({"password": "updated-test-password"})
        flow.async_update_reload_and_abort.assert_not_called()

    async def test_reauth_rejects_invalid_password(self):
        flow, _, coordinator = self.flow(devices=[], login_error=ConfigEntryAuthFailed("invalid"))
        with patch.object(config_flow, "SwitchBotS10Coordinator", return_value=coordinator):
            await flow.async_step_reauth_confirm({"password": "incorrect-test-password"})
        self.assertEqual(flow.async_show_form.call_args.kwargs["errors"], {"base": "invalid_auth"})


if __name__ == "__main__":
    unittest.main()
