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

    def test_reload_message_requests_fresh_device_config(self):
        callback = Mock()
        self.client.device_config_reload_callback = callback
        self.client.on_message(self.client.client, None, SimpleNamespace(
            topic="tenant/org/gateway/gw/device/config/reload", payload=b"{}"))
        callback.assert_called_once_with()

    def test_reports_applied_profile_revision(self):
        self.assertTrue(self.client.publish_device_config_applied([{
            "_id": "device-1", "deviceProfileId": {
                "_id": "profile-1", "updatedAt": "2026-10-20T10:00:00.000Z",
            },
        }]))
        args, kwargs = self.client.client.publish.call_args
        self.assertEqual(args[0], "tenant/org/gateway/gw/device/config/applied")
        self.assertEqual(json.loads(args[1])["devices"], [{
            "deviceId": "device-1", "profileId": "profile-1",
            "profileRevision": "2026-10-20T10:00:00.000Z",
        }])
        self.assertEqual(kwargs, {"qos": 1, "retain": False})

    def test_device_result_waits_for_broker_ack(self):
        self.info.is_published.return_value = False
        self.assertFalse(self.client.publish_device_command_result("pump", "one", "success", "restart"))
        self.info.wait_for_publish.assert_called_once_with(timeout=2)

    def test_device_status_reports_the_configured_channel_without_brand_fields(self):
        self.client.on_change_device_connection(
            "pump", "online", None, "auxiliary", channel_status="online"
        )
        args, kwargs = self.client.client.publish.call_args
        self.assertEqual(args[0], "tenant/org/gateway/gw/device/pump/status")
        self.assertEqual(json.loads(args[1]), {
            "status": "online",
            "channelStatus": "online",
            "connectionReason": None,
            "channel": "auxiliary",
            "failedRegisters": [],
        })
        self.assertEqual(kwargs, {"qos": 1, "retain": False})

    def test_sent_signal_snapshot_tracks_actual_publish_and_broker_ack(self):
        signal = {"channelId": "main", "payload": {"curr": {"value": 8.5, "rawValue": 85}}}
        topic = {"organization_id": "org", "gateway_id": "gw", "serial_number": "pump"}
        self.info.is_published.return_value = False

        self.assertTrue(self.client.send_signal(topic, signal))
        args, kwargs = self.client.client.publish.call_args
        self.assertEqual(args[0], "tenant/org/gateway/gw/device/pump/signal")
        self.assertEqual(json.loads(args[1]), signal)
        self.assertEqual(kwargs, {"qos": 1, "retain": False})
        pending = self.client.sent_signals_snapshot()[0]
        self.assertEqual(pending["delivery"], "unconfirmed")
        self.assertEqual(pending["payload"]["curr"]["value"], 8.5)

        self.info.is_published.return_value = True
        self.assertEqual(self.client.sent_signals_snapshot()[0]["delivery"], "confirmed")
        self.client.clear_sent_signals()
        self.assertEqual(self.client.sent_signals_snapshot(), [])

    def test_failed_signal_publish_is_not_reported_as_sent(self):
        self.info.rc = 4
        topic = {"organization_id": "org", "gateway_id": "gw", "serial_number": "pump"}
        self.assertFalse(self.client.send_signal(topic, {
            "channelId": "main", "payload": {"fault": {"value": 1}},
        }))
        self.assertEqual(self.client.sent_signals_snapshot()[0]["delivery"], "failed")

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
