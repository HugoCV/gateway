"""MQTT boundary tests with no broker, credentials or hardware dependencies."""
import importlib.util
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class GatewayCommandMqttTests(unittest.TestCase):
    def setUp(self):
        mqtt = SimpleNamespace(Client=Mock, MQTT_ERR_SUCCESS=0, topic_matches_sub=Mock())
        modules = {
            "certifi": SimpleNamespace(),
            "bson": SimpleNamespace(ObjectId=Mock),
            "paho": SimpleNamespace(),
            "paho.mqtt": SimpleNamespace(client=mqtt),
            "paho.mqtt.client": mqtt,
            "infrastructure.config.loader": SimpleNamespace(load_config=lambda: {"MQTT_HOST": "test", "MQTT_PORT": 1883}),
        }
        spec = importlib.util.spec_from_file_location("mqtt_command_test",
            Path(__file__).resolve().parents[1] / "infrastructure/mqtt/mqtt_client.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)
        self.client = module.MqttClient({"organizationId": "org", "gatewayId": "gw"},
                                       Mock(), Mock(), Mock(), Mock(), Mock())
        self.client.client = Mock()
        self.client._connected_evt.set()
        self.info = self.client.client.publish.return_value
        self.info.rc = 0
        self.info.is_published.return_value = True
        self.result = {"commandId": "restart-1", "status": "success", "reason": None}

    def test_result_uses_tenant_topic_qos_one_without_retention_and_waits_for_ack(self):
        self.assertTrue(self.client.publish_gateway_command_result(self.result))
        args, kwargs = self.client.client.publish.call_args
        self.assertEqual(args[0], "tenant/org/gateway/gw/command/result")
        self.assertEqual(json.loads(args[1]), self.result)
        self.assertEqual(kwargs, {"qos": 1, "retain": False})
        self.info.wait_for_publish.assert_called_once_with(timeout=2)

    def test_no_ack_is_not_success(self):
        self.info.is_published.return_value = False
        self.assertFalse(self.client.publish_gateway_command_result(self.result))

    def test_disconnected_client_keeps_result_for_retry(self):
        self.client._connected_evt.clear()
        self.assertFalse(self.client.publish_gateway_command_result(self.result))
        self.client.client.publish.assert_not_called()

    def test_refused_connection_never_confirms_restart(self):
        self.client.on_connect(self.client.client, None, {}, 5)
        self.assertFalse(self.client._connected_evt.is_set())
        self.client.on_initial_load.assert_not_called()
        self.client.gateway_results_callback.assert_not_called()

    def test_outbox_is_flushed_by_heartbeat_not_network_callback(self):
        self.client.on_connect(self.client.client, None, {}, 0)
        self.client.gateway_results_callback.assert_not_called()
        self.client._stop_event = Mock(spec=threading.Event)
        self.client._stop_event.wait.side_effect = [False, True]
        self.client._heartbeat_loop()
        self.client.gateway_results_callback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
