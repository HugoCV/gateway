import json
import threading
import ssl
import time
from datetime import datetime
from typing import Any, Dict, Optional, Callable

import certifi
from paho.mqtt import client as mqtt
from bson import ObjectId

from infrastructure.config.loader import load_config, get_gateway

cfg = load_config()
gateway_cfg = get_gateway()

MQTT_HOST = cfg["MQTT_HOST"]
MQTT_PORT = int(cfg["MQTT_PORT"])
MQTT_USER = cfg.get("MQTT_USER")
MQTT_PASS = cfg.get("MQTT_PASS")


class MqttClient:
    def __init__(
        self,
        log_callback: Callable[[str], None],
        stop_callback: Callable[[], None],
        start_callback: Callable[[], None],
        reset_callback: Callable[[], None],
    ) -> None:
        self.log = log_callback
        self.stop_device = stop_callback
        self.start_device = start_callback
        self.reset_device = reset_callback

        self.client: Optional[mqtt.Client] = None
        self._loop_started = False
        self._connect_thread: Optional[threading.Thread] = None
        self._connected_evt = threading.Event()

        self._log_initial_config()

    # ---------- Helpers ----------
    def _log_initial_config(self) -> None:
        self.log(f"🔧 MQTT -> host={MQTT_HOST}, port={MQTT_PORT}")

    @staticmethod
    def _is_valid_objectid(v: str) -> bool:
        try:
            ObjectId(v)
            return True
        except Exception:
            return False

    @staticmethod
    def _get(gw: Dict[str, Any], *keys: str) -> Optional[str]:
        """Retrieve value from gateway config supporting both snake_case and camelCase."""
        for k in keys:
            val = gw.get(k)
            if val:
                return str(val)
        return None

    def _topic_cmd(self, org_id: str, gw_id: str) -> str:
        """Build MQTT command topic."""
        return f"tenant/{org_id}/gateway/{gw_id}/device/+/command"

    def _topic_signal(self, org_id: str, gw_id: str, serial: str) -> str:
        """Build MQTT signal topic."""
        return f"tenant/{org_id}/gateway/{gw_id}/device/{serial}/signal"

    def _topic_device(self, org_id: str, gw_id: str, serial: str) -> str:
        """Build MQTT device info topic."""
        return f"tenant/{org_id}/gateway/{gw_id}/device/{serial}/device"

    # ---------- Connection ----------
    def connect(self, broker: str = MQTT_HOST, port: int = MQTT_PORT) -> None:
        """Create the client, configure TLS/LWT and start loop in background."""
        if self._connect_thread and self._connect_thread.is_alive():
            self.log("⚠️ MQTT connection already in progress.")
            return

        def _run() -> None:
            client_id = f"gateway_py_{self._get(gateway_cfg,'gatewayId','gateway_id') or ObjectId()}"
            self.client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv5)

            # Credentials
            if MQTT_USER and MQTT_PASS:
                self.client.username_pw_set(MQTT_USER, MQTT_PASS)
                self.log("🔑 Credentials set")

            # Last Will and Testament (online status)
            lwt_topic = f"tenant/{self._get(gateway_cfg,'organizationId','organization_id')}/status"
            self.client.will_set(lwt_topic, json.dumps({"online": False}), qos=1, retain=False)

            # TLS if using port 8883
            if port == 8883:
                try:
                    ca = certifi.where()
                    self.client.tls_set(ca_certs=ca, tls_version=ssl.PROTOCOL_TLS_CLIENT)
                    self.client.tls_insecure_set(False)
                    self.log("🔒 TLS configured")
                except Exception as e:
                    self.log(f"❌ TLS error: {e}")
                    return

            # Callbacks
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.on_message = self.on_message
            self.client.on_log = self.on_log

            # Connection with exponential backoff
            delay = 1.0
            while True:
                try:
                    self.client.connect(broker, port, keepalive=30)
                    if not self._loop_started:
                        self.client.loop_start()
                        self._loop_started = True
                        self.log("⌛ MQTT loop started")
                    break
                except Exception as e:
                    self.log(f"❌ Connection error: {e} — retrying in {delay:.0f}s")
                    time.sleep(delay)
                    delay = min(delay * 2, 30)

        self._connect_thread = threading.Thread(target=_run, daemon=True)
        self._connect_thread.start()

    def disconnect(self) -> None:
        """Disconnect the MQTT client and stop loop."""
        if self.client:
            try:
                self.client.loop_stop()
            except Exception:
                pass
            try:
                self.client.disconnect()
            except Exception:
                pass
            self._loop_started = False
            self.log("👋 MQTT disconnected")

    # ---------- Paho callbacks ----------
    def on_connect(self, client: mqtt.Client, userdata, flags, reason_code, properties=None) -> None:
        """MQTT on_connect callback."""
        self.log(f"✅ Connected (rc={reason_code})")
        org_id = self._get(gateway_cfg, "organizationId", "organization_id")
        gw_id = self._get(gateway_cfg, "gatewayId", "gateway_id")

        if not org_id or not gw_id:
            self.log("⚠️ Missing organizationId / gatewayId in config")
            return

        topic = self._topic_cmd(org_id, gw_id)
        client.subscribe(topic, qos=1)
        self.log(f"📡 Subscribed to commands: {topic}")

        # Publish online status
        online_topic = f"tenant/{org_id}/status"
        self._publish(online_topic, json.dumps({"online": True}), qos=1)

        self._connected_evt.set()

    def on_disconnect(self, client: mqtt.Client, userdata, flags, reason_code, properties=None) -> None:
        """MQTT on_disconnect callback."""
        self.log(f"⚠️ Disconnected (rc={reason_code})")
        self._connected_evt.clear()

    def on_log(self, client, userdata, level, buf) -> None:
        """MQTT on_log callback."""
        if level >= mqtt.MQTT_LOG_INFO:
            self.log(f"[MQTT-{level}] {buf}")

    def on_message(self, client: mqtt.Client, userdata, msg) -> None:
        """MQTT on_message callback."""
        print("on_message")
        topic = msg.topic
        try:
            payload = msg.payload.decode("utf-8")
            cmd = json.loads(payload)

            action = cmd.get("action")
            value = cmd.get("params", {}).get("value")

            if value == 0:
                self.stop_device()
            elif value == 1:
                self.start_device()
            elif value == 2:
                self.reset_device()

            self.log(f"📥 Command on {topic}: action={action}, value={value}")
        except Exception as e:
            self.log(f"❌ Error processing message on {topic}: {e}")

    # ---------- Publish utilities ----------
    def _publish(self, topic: str, payload: str, qos: int = 1) -> None:
        """Publish a message to a topic."""
        if not self.client:
            self.log("⚠️ MQTT client not ready to publish.")
            return
        try:
            info = self.client.publish(topic, payload, qos=qos)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                self.log(f"⚠️ publish() failed rc={info.rc} topic={topic}")
        except Exception as e:
            self.log(f"❌ Error publishing to {topic}: {e}")

    # ---------- Public API ----------
    def send_signal(self, topic_info: Dict[str, str], signal_info: Dict[str, Any]) -> None:
        """Publish device signal payload."""
        org_id = topic_info.get("organization_id") or topic_info.get("organizationId")
        gw_id = topic_info.get("gateway_id") or topic_info.get("gatewayId")
        serial = topic_info.get("serial_number") or topic_info.get("serialNumber")

        if not (org_id and gw_id and serial):
            self.log(f"⚠️ Missing topic info: {topic_info}")
            return

        topic = self._topic_signal(org_id, gw_id, serial)
        self._publish(topic, json.dumps(signal_info, default=str), qos=1)
        print("signal enviada", signal_info)
        self.log(f"📤 Signal → {topic}")

    def save_device(self, organization_id: str, gateway_id: str, device: Dict[str, Any]) -> None:
        """Publish device metadata/status payload."""
        serial = str(device.get("serialNumber") or device.get("serial_number") or "").strip()
        if not serial:
            self.log("⚠️ Device missing serialNumber")
            return
        topic = self._topic_device(organization_id, gateway_id, serial)
        self._publish(topic, json.dumps(device, default=str), qos=1)
        self.log(f"📤 Device → {topic}")

    def send_gateway_register(self, name: str = "gateway", location: str = "unknown") -> None:
        """Send gateway registration request."""
        org_id = self._get(gateway_cfg, "organizationId", "organization_id") or ""
        gw_id = self._get(gateway_cfg, "gatewayId", "gateway_id") or str(ObjectId())
        if not self._is_valid_objectid(gw_id):
            gw_id = str(ObjectId())

        data = {
            "name": name,
            "organizationId": org_id,
            "location": location,
            "gatewayId": gw_id,
            "timestamp": datetime.utcnow().isoformat(),
        }
        topic = f"tenant/{org_id}/gateway/register/request"
        info = self.client.publish(topic, json.dumps(data), qos=1)
        info.wait_for_publish()
        if info.rc == mqtt.MQTT_ERR_SUCCESS:
            self.log(f"▶ Registration sent → {topic} (mid={info.mid})")
        else:
            self.log(f"❌ publish() failed rc={info.rc}")

    def request_gateway_config(self, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """Publish a config request and wait for a single response with timeout."""
        if not self.client:
            self.log("⚠️ MQTT client not initialized.")
            return None

        org_id = self._get(gateway_cfg, "organizationId", "organization_id") or ""
        gw_id = self._get(gateway_cfg, "gatewayId", "gateway_id") or ""
        req_topic = f"tenant/{org_id}/gateway/{gw_id}/config/request"
        resp_topic = f"tenant/{org_id}/gateway/{gw_id}/config/response"

        response: Dict[str, Any] = {}
        received = threading.Event()

        def _on_config_response(client, userdata, msg):
            try:
                payload = msg.payload.decode("utf-8")
                response.update(json.loads(payload))
            finally:
                received.set()

        self.client.subscribe(resp_topic, qos=1)
        self.client.message_callback_add(resp_topic, _on_config_response)

        payload = json.dumps({"timestamp": time.time()})
        self.client.publish(req_topic, payload, qos=1)
        self.log(f"▶ Config request → {req_topic}")

        ok = received.wait(timeout)
        self.client.message_callback_remove(resp_topic)

        if not ok:
            self.log(f"⚠️ No config response within {timeout}s.")
            return None
        return response
