import unittest
from unittest.mock import Mock

from application.services.device_service import DeviceService


class DeviceServiceStatusTests(unittest.TestCase):
    def test_global_status_respects_minimum_channels_and_keeps_channel_status(self):
        service = object.__new__(DeviceService)
        service.profile = {"connectionPolicy": {"minimumEnabledChannels": 2}}
        service.channel_status = {}
        service.connected = False
        service.connected_logo = False
        service.serial = "drive-1"
        service.mqtt = Mock()

        service._on_channel_status("main", True, None, [])
        first = service.mqtt.on_change_device_connection.call_args
        self.assertEqual(first.args[1], "offline")
        self.assertEqual(first.kwargs["channel_status"], "online")

        service._on_channel_status("backup", True, None, [])
        second = service.mqtt.on_change_device_connection.call_args
        self.assertEqual(second.args[1], "online")
        self.assertEqual(second.kwargs["channel_status"], "online")

        service._on_channel_status("main", False, "connection_failed", [])
        third = service.mqtt.on_change_device_connection.call_args
        self.assertEqual(third.args[1], "offline")
        self.assertEqual(third.kwargs["channel_status"], "offline")


if __name__ == "__main__":
    unittest.main()
