"""A profile reload must not interrupt unrelated running devices."""
import json
import unittest
from unittest.mock import Mock, patch

from application.app_controller import AppController
from application.managers.device_manager import DeviceManager


class ProfileReloadTests(unittest.TestCase):
    def test_multi_batch_response_applies_only_after_all_batches(self):
        mqtt, refresh = Mock(), Mock()
        manager = DeviceManager(mqtt, refresh)
        manager.load_devices()
        callback = mqtt.request_devices.call_args.args[0]

        def response(index, serial):
            return Mock(payload=json.dumps({
                "index": index, "total": 2, "devices": [{"serialNumber": serial}],
            }).encode())

        self.assertFalse(callback(None, None, response(1, "PUMP-2")))
        refresh.assert_not_called()
        self.assertTrue(callback(None, None, response(0, "PUMP-1")))
        refresh.assert_called_once_with([{"serialNumber": "PUMP-1"}, {"serialNumber": "PUMP-2"}])

    def test_unchanged_device_service_is_reused(self):
        controller = object.__new__(AppController)
        controller.mqtt_handler = Mock()
        controller.gateway_cfg = {}
        controller.log = Mock()
        original = Mock()
        original.device = {
            "name": "Bomba", "serialNumber": "PUMP-1", "deviceProfileId": {"updatedAt": "v1"},
            "connections": [], "parameters": {}, "commissioningStatus": "active",
        }
        controller.devices = {"PUMP-1": original}

        with patch("application.app_controller.DeviceService") as service_class:
            result = controller.create_all_devices([dict(original.device, status="online")])

        self.assertIs(result["PUMP-1"], original)
        original.stop.assert_not_called()
        service_class.assert_not_called()

    def test_changed_profile_rebuilds_only_affected_device(self):
        controller = object.__new__(AppController)
        controller.mqtt_handler = Mock()
        controller.gateway_cfg = {}
        controller.log = Mock()
        original = Mock()
        original.device = {
            "name": "Bomba", "serialNumber": "PUMP-1", "deviceProfileId": {"updatedAt": "v1"},
            "connections": [], "parameters": {}, "commissioningStatus": "active",
        }
        controller.devices = {"PUMP-1": original}

        with patch("application.app_controller.DeviceService") as service_class:
            service_class.return_value.serial = "PUMP-1"
            result = controller.create_all_devices([dict(original.device, deviceProfileId={"updatedAt": "v2"})])

        original.stop.assert_called_once_with()
        self.assertIs(result["PUMP-1"], service_class.return_value)


if __name__ == "__main__":
    unittest.main()
