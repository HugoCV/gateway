import json
import threading
import ssl
import time
from typing import Any, Dict, Optional, Callable

import certifi
from paho.mqtt import client as mqtt
from paho.mqtt.client import topic_matches_sub
from bson import ObjectId

from infrastructure.config.loader import load_config

cfg = load_config()

MQTT_HOST = cfg["MQTT_HOST"]
MQTT_PORT = int(cfg["MQTT_PORT"])
MQTT_USER = cfg.get("MQTT_USER")
MQTT_PASS = cfg.get("MQTT_PASS")


class MqttClient:
    def __init__(
        self,
        gateway: Dict[str, Any],
        on_initial_load: Callable[[], None],
        log_callback: Callable[[str], None],
        command_callback: Callable[[Optional[str], Any], None],
        command_gateway_callback: Callable[[Optional[str], Any], None]
    ) -> None:
        self.log = log_callback
        self.command_gateway_callback = command_gateway_callback
        self.command_callback = command_callback
        self.on_initial_load = on_initial_load

        self.client: Optional[mqtt.Client] = None
        self._loop_started = False
        self._connect_thread: Optional[threading.Thread] = None
        self._connected_evt = threading.Event()
        self._stop_event = threading.Event()

        self.gateway = gateway
        self._cfg_ev = threading.Event()
        self._cfg_out: Dict[str, Any] = {}

        # Cache org/gw ids
        self.org_id = self._get(self.gateway, "organizationId", "organization_id")
        self.gw_id = self._get(self.gateway, "gatewayId", "gateway_id")
        if not self.org_id or not self.gw_id:
            self.log("⚠️ Missing organizationId / gatewayId in config")

        # Topics (convenience variables built once)
        self.deviceCommandTopic = self._topic_subscribe_command(self.org_id, self.gw_id)
        self.gatewayCommandTopic = self._topic_subscribe_gateway_command(self.org_id, self.gw_id)
        self.gatewayRespTopic = self._topic_subscribe_gateway_resp(self.org_id, self.gw_id)
        self.gatewayReqTopic = self._topic_publish_gateway_req(self.org_id, self.gw_id)
        self.deviceReqTopic = self._topic_publish_device_req(self.org_id, self.gw_id)
        self.deviceRespTopic = self._topic_subscribe_device_resp(self.org_id, self.gw_id)

        self._log_initial_config()

    # ---------- Helpers ----------
    def _log_initial_config(self) -> None:
        self.log(f"🔧 MQTT -> host={MQTT_HOST}, port={MQTT_PORT}")

    @staticmethod
    def _get(gw: Dict[str, Any], *keys: str) -> Optional[str]:
        for k in keys:
            val = gw.get(k)
            if val:
                return str(val)
        return None

    # --- Topic builders (only used in __init__) ---
    def _topic_publish_signal(self, org_id: str, gw_id: str, serial: str) -> str:
        return f"tenant/{org_id}/gateway/{gw_id}/device/{serial}/signal"

    def _topic_publish_device_update(self, org_id: str, gw_id: str, serial: str) -> str:
        return f"tenant/{org_id}/gateway/{gw_id}/device/{serial}/device"

    def _topic_publish_gateway_update(self, org_id: str, gw_id: str) -> str:
        return f"tenant/{org_id}/gateway/{gw_id}/update"

    def _topic_subscribe_command(self, org_id: str, gw_id: str) -> str:
        return f"tenant/{org_id}/gateway/{gw_id}/device/+/command"

    def _topic_subscribe_gateway_command(self, org_id: str, gw_id: str) -> str:
        return f"tenant/{org_id}/gateway/{gw_id}/command"

    def _topic_subscribe_gateway_resp(self, org_id: str, gw_id: str) -> str:
        return f"tenant/{org_id}/gateway/{gw_id}/config/response"

    def _topic_publish_gateway_req(self, org_id: str, gw_id: str) -> str:
        return f"tenant/{org_id}/gateway/{gw_id}/config/request"

    def _topic_publish_device_req(self, org_id: str, gw_id: str) -> str:
        return f"tenant/{org_id}/gateway/{gw_id}/device/request"

    def _topic_subscribe_device_resp(self, org_id: str, gw_id: str) -> str:
        return f"tenant/{org_id}/gateway/{gw_id}/device/response"
    
    def _topic_publish_device_status(self, org_id:str, gw_id: str, serial:str) -> str:
        return f"tenant/{org_id}/gateway/{gw_id}/device/{serial}/status"

    # ---------- Connection ----------
    def connect(self) -> None:
        """Configura el cliente, TLS/LWT y activa auto-reconnect en background."""
        broker = MQTT_HOST
        port = MQTT_PORT
        if not broker:
            self.log("MQTT_HOST not configured")
            return

        client_id = f"gateway_py_{self.gw_id or ObjectId()}"
        self.client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv5)

        if MQTT_USER and MQTT_PASS:
            self.client.username_pw_set(MQTT_USER, MQTT_PASS)
            self.log("🔐 Credentials set")

        lwt_topic = f"tenant/{self.org_id}/gateway/{self.gw_id}/status"
        self.client.will_set(lwt_topic, json.dumps({"status": "offline"}), qos=1, retain=False)

        if port == 8883:
            ca = certifi.where()
            self.client.tls_set(ca_certs=ca, tls_version=ssl.PROTOCOL_TLS_CLIENT)
            self.client.tls_insecure_set(False)
            self.log("🔒 TLS configured")

        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.on_log = self.on_log

        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

        self.client.connect_async(broker, port, keepalive=30)
        if not self._loop_started:
            self.client.loop_start()
            self._loop_started = True
            self.log("⌛ MQTT loop started (auto-reconnect enabled)")

    def disconnect(self) -> None:
        """Disconnect the MQTT client and stop loop."""
        self._stop_event.set()
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
        self.log(f"✅ Connected (rc={reason_code})")

        if not self.org_id or not self.gw_id:
            self.log("⚠️ Missing organizationId / gatewayId in config")
            return

        client.subscribe(self.deviceCommandTopic, qos=1)
        self.log(f"Subscribed to commands: {self.deviceCommandTopic}")

        client.subscribe(self.gatewayCommandTopic, qos=1)
        self.log(f"Subscribed to commands: {self.gatewayCommandTopic}")
        # Publish online status
        online_topic = f"tenant/{self.org_id}/gateway/{self.gw_id}/status"
        self._publish(online_topic, json.dumps({"status": "online"}), qos=1)
        self.on_initial_load()
        self._connected_evt.set()

    def on_change_device_connection(self, device_serial, status, logo_status):
        print(f"Dispositivo {device_serial} {status}")
        device_connection_topic = self._topic_publish_device_status(self.org_id, self.gw_id, device_serial)
        self._publish(device_connection_topic, json.dumps({"status": status, "logoStatus": logo_status}), qos=1)

    def on_disconnect(self, client: mqtt.Client, userdata, flags, reason_code, properties=None) -> None:
        print("on_disconnect mqtt")
        self.log(f"⚠️ Disconnected (rc={reason_code})")
        self._connected_evt.clear()

    def on_log(self, client, userdata, level, buf) -> None:
        if level >= mqtt.MQTT_LOG_INFO:
            self.log(f"[MQTT-{level}] {buf}")

    def on_message(self, client, userdata, msg):
        print("ON MESSAGE")
        if topic_matches_sub(self.deviceCommandTopic, msg.topic):
            parts = msg.topic.split("/")
            try:
                dev_idx = parts.index("device") + 1
                device_id = parts[dev_idx]
            except Exception:
                device_id = None
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
            except Exception:
                payload = msg.payload  # raw if not JSON
            self.command_callback(device_id, payload)
            self.log(f"[MQTT-CMD] device={device_id} payload={payload}")
            return
        if topic_matches_sub(self.gatewayCommandTopic, msg.topic):

            parts = msg.topic.split("/")
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
            except Exception:
                payload = msg.payload
            self.command_gateway_callback(payload)
            self.log(f"[MQTT-CMD] payload={payload}")
            return

        # Config response
        if msg.topic == self.gatewayRespTopic and self._cfg_ev is not None:
            try:
                data = json.loads(msg.payload.decode("utf-8"))
            except Exception as e:
                self.log(f"[CFG] json error: {e}")
                return
            self._cfg_out.clear()
            self._cfg_out.update(data)
            self._cfg_ev.set()
            self.log("[CFG] ✓ response captured")
            return

        # Other
        self.log(f"[RX] {msg.topic} ({len(msg.payload)} bytes)")

    # ---------- Publish utilities ----------
    def _publish(self, topic: str, payload: str, qos: int = 1) -> bool:
        if not self.client:
            self.log("⚠️ MQTT client not ready to publish.")
            return False
        try:
            info = self.client.publish(topic, payload, qos=qos)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                self.log(f"⚠️ publish() failed rc={info.rc} topic={topic}")
                print(self.log(f"⚠️ publish() failed rc={info.rc} topic={topic}"))
                return False
            return True
        except Exception as e:
            self.log(f"❌ Error publishing to {topic}: {e}")
            return False

    # ---------- Public API ----------
    def send_signal(self, topic_info: Dict[str, str], signal_info: Dict[str, Any]) -> None:
        org_id = topic_info.get("organization_id") or topic_info.get("organizationId")
        gw_id = topic_info.get("gateway_id") or topic_info.get("gatewayId")
        serial = topic_info.get("serial_number") or topic_info.get("serialNumber")

        if not (org_id and gw_id and serial):
            self.log(f"⚠️ Missing topic info: {topic_info}")
            return

        topic = self._topic_publish_signal(org_id, gw_id, serial)
        if self._publish(topic, json.dumps(signal_info, default=str), qos=1):
            self.log(f"📤 Signal → {topic}")

    def on_send_signal(self, results: Dict[str, Any], group: str) -> None:
        try:
            if not isinstance(results, dict) or not results:
                self.log("⚠️ Resultado vacío o no es dict; no se envía MQTT.")
                return

            serial = (self.window.serial_var.get() or "").strip()
            if not serial:
                self.log("⚠️ Serial vacío; se omite envío MQTT.")
                return

            org_id = self.gateway_cfg.get("organization_id") or self.gateway_cfg.get("organizationId")
            gw_id = self.gateway_cfg.get("gateway_id") or self.gateway_cfg.get("gatewayId")
            if not org_id or not gw_id:
                self.log(f"⚠️ Faltan IDs en gateway_cfg: org={org_id} gw={gw_id}")
                return

            topic_info = {
                "serial_number": serial,
                "organization_id": org_id,
                "gateway_id": gw_id,
            }
            signal = {"group": group, "payload": results}
            self.send_signal(topic_info, signal)
        except Exception as e:
            self.log(f"❌ on_send_signal error: {e}")

    def request_gateway_config(self, cb: Callable) -> None:
        self.client.message_callback_add(self.gatewayRespTopic, cb)
        self.client.subscribe(self.gatewayRespTopic, qos=1)
        self.client.publish(self.gatewayReqTopic, json.dumps({"timestamp": time.time()}), qos=1)

    def request_devices(self, cb: Callable) -> None:
        self.client.message_callback_add(self.deviceRespTopic, cb)
        self.client.subscribe(self.deviceRespTopic, qos=1)
        self.client.publish(self.deviceReqTopic, json.dumps({"timestamp": time.time()}), qos=1)
