import unittest
from unittest.mock import Mock, patch

from application.services.device_service import DeviceService


class DeviceServiceStatusTests(unittest.TestCase):
    @patch("application.services.device_service.ConfiguredModbusChannel")
    def test_commissioning_devices_build_and_start_enabled_channels(self, channel_class):
        channel = channel_class.return_value
        service = DeviceService(
            mqtt_handler=Mock(),
            gateway_cfg={},
            device={
                "_id": "device-1",
                "name": "Drive",
                "serialNumber": "drive-1",
                "commissioningStatus": "commissioning",
                "deviceProfileId": {"channels": [{"id": "main", "protocol": "modbus-tcp", "items": []}]},
                "connections": [{"channelId": "main", "enabled": True, "host": "127.0.0.1", "port": 502}],
            },
            log=Mock(),
            update_fields=None,
        )

        channel_class.assert_called_once()
        channel.start.assert_called_once()
        service.stop()

    def test_global_status_respects_minimum_channels_and_keeps_channel_status(self):
        service = object.__new__(DeviceService)
        service.profile = {"connectionPolicy": {"minimumEnabledChannels": 2}}
        service.channel_status = {}
        service.connected = False
        service.serial = "drive-1"
        service.mqtt = Mock()

        service._on_channel_status("main", True, None, [])
        first = service.mqtt.on_change_device_connection.call_args
        self.assertEqual(first.args[1], "offline")
        self.assertEqual(first.args[3], "main")
        self.assertEqual(first.kwargs["channel_status"], "online")

        service._on_channel_status("backup", True, None, [])
        second = service.mqtt.on_change_device_connection.call_args
        self.assertEqual(second.args[1], "online")
        self.assertEqual(second.args[3], "backup")
        self.assertEqual(second.kwargs["channel_status"], "online")

        service._on_channel_status("main", False, "connection_failed", [])
        third = service.mqtt.on_change_device_connection.call_args
        self.assertEqual(third.args[1], "offline")
        self.assertEqual(third.kwargs["channel_status"], "offline")


if __name__ == "__main__":
    unittest.main()
