import json
import threading
import ssl
import time
from datetime import datetime
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
        gateway,
        on_initial_load,
        log_callback: Callable[[str], None],
        command_callback: Callable[[], None]
    ) -> None:
        self.log = log_callback
        self.command_callback = command_callback
        
        self.on_initial_load = on_initial_load
        self.client: Optional[mqtt.Client] = None
        self._loop_started = False
        self._connect_thread: Optional[threading.Thread] = None
        self._connected_evt = threading.Event()
        self.gateway = gateway
        
        self._cfg_ev  = threading.Event()
        self._cfg_out = {}
        org_id = self.gateway['organizationId']
        gw_id = self.gateway['gatewayId']

        self.deviceCommandTopic = f"tenant/{org_id}/gateway/{gw_id}/device/+/command"
        self.gatewayRespTopic = f"tenant/{org_id}/gateway/{gw_id}/config/response"
        self.gatewayReqTopic = f"tenant/{org_id}/gateway/{gw_id}/config/request"
        self.deviceReqTopic = f"tenant/{org_id}/gateway/{gw_id}/device/request"
        self.deviceRespTopic = f"tenant/{org_id}/gateway/{gw_id}/device/response"

        self._log_initial_config()

    # ---------- Helpers ----------
    def _log_initial_config(self) -> None:
        self.log(f"🔧 MQTT -> host={MQTT_HOST}, port={MQTT_PORT}")

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
    def connect(self) -> None:
        """Create the client, configure TLS/LWT and start loop in background."""
        broker = MQTT_HOST
        port = MQTT_PORT
        print(broker, port)
        if not broker:
            self.log("Error", "Debes ingresar un broker.")
            return
        if self._connect_thread and self._connect_thread.is_alive():
            self.log("⚠️ MQTT connection already in progress.")
            return

        def _run() -> None:
            client_id = f"gateway_py_{self._get(self.gateway,'gatewayId','gateway_id') or ObjectId()}"
            self.client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv5)

            if MQTT_USER and MQTT_PASS:
                self.client.username_pw_set(MQTT_USER, MQTT_PASS)
                self.log("🔑 Credentials set")

            lwt_topic = f"tenant/{self._get(self.gateway,'organizationId','organization_id')}/status"
            self.client.will_set(lwt_topic, json.dumps({"online": False}), qos=1, retain=False)

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
        org_id = self._get(self.gateway, "organizationId", "organization_id")
        gw_id = self._get(self.gateway, "gatewayId", "gateway_id")

        if not org_id or not gw_id:
            self.log("⚠️ Missing organizationId / gatewayId in config")
            return

        topic = self._topic_cmd(org_id, gw_id)
        client.subscribe(topic, qos=1)
        self.log(f"📡 Subscribed to commands: {topic}")

        # Publish online status
        online_topic = f"tenant/{org_id}/status"
        self._publish(online_topic, json.dumps({"online": True}), qos=1)
        self.on_initial_load()
        self._connected_evt.set()

    def on_disconnect(self, client: mqtt.Client, userdata, flags, reason_code, properties=None) -> None:
        """MQTT on_disconnect callback."""
        self.log(f"⚠️ Disconnected (rc={reason_code})")
        self._connected_evt.clear()

    def on_log(self, client, userdata, level, buf) -> None:
        """MQTT on_log callback."""
        if level >= mqtt.MQTT_LOG_INFO:
            self.log(f"[MQTT-{level}] {buf}")

    def on_message(self, client, userdata, msg):
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
            print(f"[CMD] device_id={device_id} topic={msg.topic} payload={payload}")
            return

        # 2) Config response (exact topic)
        if msg.topic == self.reqTopic and self._cfg_ev is not None:
            try:
                data = json.loads(msg.payload.decode("utf-8"))
            except Exception as e:
                print("[CFG] json error:", e)
                return
            self._cfg_out.clear()
            self._cfg_out.update(data)
            self._cfg_ev.set()
            print("[CFG] ✓ response captured")
            return

        # 3) Anything else (optional)
        print(f"[RX] {msg.topic} ({len(msg.payload)} bytes)")

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


    def on_send_signal(self, results, group):
        """
        results: dict con lecturas
        group:   'drive' | 'logo' | etc.
        """
        try:
            if not isinstance(results, dict) or not results:
                self.log("⚠️ Resultado vacío o no es dict; no se envía MQTT.")
                return

            serial = (self.window.serial_var.get() or "").strip()
            if not serial:
                self.log("⚠️ Serial vacío; se omite envío MQTT.")
                return

            # Acepta organization_id/organizationId y gateway_id/gatewayId
            org_id = self.gateway_cfg.get("organization_id") or self.gateway_cfg.get("organizationId")
            gw_id  = self.gateway_cfg.get("gateway_id") or self.gateway_cfg.get("gatewayId")
            if not org_id or not gw_id:
                self.log(f"⚠️ Faltan IDs en gateway_cfg: org={org_id} gw={gw_id}")
                return

            topic_info = {
                "serial_number":  serial,
                "organization_id": org_id,
                "gateway_id":      gw_id,
            }
            signal = {"group": group, "payload": results}
            self.send_signal(topic_info, signal)
        except Exception as e:
            # mensaje correcto para esta función
            self.log(f"❌ on_send_signal error: {e}")


    def request_gateway_config(self, cb):
        self.client.message_callback_add(self.gatewayRespTopic, cb)
        self.client.subscribe(self.gatewayRespTopic, qos=1)
        self.client.publish(self.gatewayReqTopic, json.dumps({"timestamp": time.time()}), qos=1)

    def request_devices(self, cb):

        self.client.message_callback_add(self.deviceRespTopic, cb)
        self.client.subscribe(self.deviceRespTopic, qos=1)
        self.client.publish(self.deviceReqTopic, json.dumps({"timestamp": time.time()}), qos=1)
