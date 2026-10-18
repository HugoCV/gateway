"""Configuration requests must survive a backend that starts after the gateway."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class MqttConfigRetryTests(unittest.TestCase):
    def setUp(self):
        mqtt = SimpleNamespace(Client=Mock, MQTT_ERR_SUCCESS=0, topic_matches_sub=Mock())
        modules = {
            "certifi": SimpleNamespace(),
            "bson": SimpleNamespace(ObjectId=Mock),
            "paho": SimpleNamespace(),
            "paho.mqtt": SimpleNamespace(client=mqtt),
            "paho.mqtt.client": mqtt,
            "infrastructure.config.loader": SimpleNamespace(
                load_config=lambda: {"MQTT_HOST": "test", "MQTT_PORT": 1883}
            ),
        }
        spec = importlib.util.spec_from_file_location(
            "mqtt_config_retry_test",
            Path(__file__).resolve().parents[1] / "infrastructure/mqtt/mqtt_client.py",
        )
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        self.addCleanup(sys.modules.pop, spec.name, None)
        self.module = module
        self.now = 100.0
        clock = patch.object(module.time, "monotonic", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.gateway = module.MqttClient(
            {"organizationId": "org", "gatewayId": "gw"},
            Mock(), Mock(), Mock(), Mock(),
        )
        self.gateway.client = Mock()
        self.gateway.client.subscribe.return_value = (0, 1)
        self.gateway.client.publish.return_value.rc = 0
        self.gateway._connected_evt.set()

    def test_retries_until_a_valid_response_then_stops(self):
        callback = Mock(return_value=True)
        self.gateway.request_gateway_config(callback)
        self.assertEqual(self.gateway.client.publish.call_count, 1)

        self.now = 104.9
        self.gateway._retry_pending_requests()
        self.assertEqual(self.gateway.client.publish.call_count, 1)
        self.now = 105
        self.gateway._retry_pending_requests()
        self.assertEqual(self.gateway.client.publish.call_count, 2)
        self.now = 115
        self.gateway._retry_pending_requests()
        self.assertEqual(self.gateway.client.publish.call_count, 3)

        response = self.gateway.client.message_callback_add.call_args.args[1]
        response(None, None, SimpleNamespace(payload=b"{}"))
        callback.assert_called_once()
        self.now = 1000
        self.gateway._retry_pending_requests()
        self.assertEqual(self.gateway.client.publish.call_count, 3)

    def test_invalid_response_keeps_retrying(self):
        callback = Mock(return_value=False)
        self.gateway.request_devices(callback)
        response = self.gateway.client.message_callback_add.call_args.args[1]
        response(None, None, SimpleNamespace(payload=b"invalid"))
        self.now = 105
        self.gateway._retry_pending_requests()
        self.assertEqual(self.gateway.client.publish.call_count, 2)

    def test_requests_retry_independently_and_later_device_batches_are_processed(self):
        config_callback = Mock(return_value=True)
        device_callback = Mock(return_value=True)
        self.gateway.request_gateway_config(config_callback)
        config_response = self.gateway.client.message_callback_add.call_args.args[1]
        self.gateway.request_devices(device_callback)
        device_response = self.gateway.client.message_callback_add.call_args.args[1]

        config_response(None, None, SimpleNamespace(payload=b"{}"))
        self.now = 105
        self.gateway._retry_pending_requests()
        self.assertEqual(self.gateway.client.publish.call_count, 3)
        self.assertEqual(self.gateway.client.publish.call_args.args[0], self.gateway.deviceReqTopic)

        device_response(None, None, SimpleNamespace(payload=b'{"index":0}'))
        device_response(None, None, SimpleNamespace(payload=b'{"index":1}'))
        self.assertEqual(device_callback.call_count, 2)
        self.now = 1000
        self.gateway._retry_pending_requests()
        self.assertEqual(self.gateway.client.publish.call_count, 3)

    def test_reconnect_replaces_old_request_callback(self):
        old_callback = Mock(return_value=True)
        new_callback = Mock(return_value=True)
        self.gateway.request_gateway_config(old_callback)
        old_response = self.gateway.client.message_callback_add.call_args.args[1]
        self.gateway.request_gateway_config(new_callback)
        old_response(None, None, SimpleNamespace(payload=b"{}"))
        old_callback.assert_not_called()
        self.now = 105
        self.gateway._retry_pending_requests()
        self.assertEqual(self.gateway.client.publish.call_count, 3)


if __name__ == "__main__":
    unittest.main()
