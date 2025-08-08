import json
import os
import threading
import ssl
import time
from datetime import datetime
import certifi
from paho.mqtt import client as mqtt
from bson import ObjectId
from bson.errors import InvalidId
from infrastructure.config.loader import load_config, get_gateway

cfg = load_config()

gateway = get_gateway()


MQTT_HOST = cfg['MQTT_HOST']
MQTT_PORT = cfg['MQTT_PORT']
MQTT_USER = cfg['MQTT_USER']
MQTT_PASS = cfg['MQTT_PASS']



class MqttClient:
    def __init__(self, log_callback, stop_callback, start_callback, reset_callback):
        self.log = log_callback
        self.stop_device = stop_callback
        self.start_device = start_callback
        self.reset_device = reset_callback
        self.client = None
        self._connected_evt = threading.Event()
        self._log_initial_config()

    def _log_initial_config(self):
        self.log(f"🔧 Config -> host={MQTT_HOST}, port={MQTT_PORT}")

    def connect(self, broker=MQTT_HOST, port=MQTT_PORT):
        self.log(f"Conectando a {broker}:{port}…")
        def _run():
            self.client = mqtt.Client(
                client_id=f"gateway_py_{gateway.get('gatewayId')}",
                protocol=mqtt.MQTTv5,
            )
            if MQTT_USER and MQTT_PASS:
                self.client.username_pw_set(MQTT_USER, MQTT_PASS)
                self.log("🔑 Credenciales configuradas")
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.on_log = self.on_log
            self.client.on_message = self.on_message

            if port == 8883:
                try:
                    ca = certifi.where()
                    self.client.tls_set(ca_certs=ca, tls_version=ssl.PROTOCOL_TLS_CLIENT)
                    self.client.tls_insecure_set(True)
                    self.log("🔒 TLS configurado")
                except Exception as e:
                    self.log(f"❌ Error TLS: {e}")
                    return
            try:
                self.client.connect(broker, port)
                self.client.loop_start()
                self.log("⌛ Loop MQTT iniciado")
            except Exception as e:
                self.log(f"❌ Error conexión: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def on_connect(self, client, userdata, flags, rc, properties=None):
        self.log(f"✅ Conectado (rc={rc})")
        org_id = gateway.get('organizationId')
        gw_id  = gateway.get('gatewayId')
        topic  = f"tenant/{org_id}/gateway/{gw_id}/device/+/command"
        client.subscribe(topic, qos=1)
        self.client = client
        print(self)
        print("client", client)
        self.log(f"📡 Suscrito a todos los comandos: {topic}")

    def on_disconnect(self, client, userdata, flags, rc, properties=None):
        self.log(f"⚠️ Desconectado (rc={rc})")

    def on_log(self, client, userdata, level, buf):
        if level >= mqtt.MQTT_LOG_INFO:
            self.log(f"[DEBUG-{level}] {buf}")

    def _publish(self, topic: str, payload: str, qos: int = 0):
        if not self.client:
            self.log("⚠ Cliente no listo.")
            return
        self.client.publish(topic, payload, qos=qos)

    def on_message(self, client, userdata, msg):
        print("llega a on message")
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        try:
            cmd = json.loads(payload)  # convierte el JSON en dict
            # Acceder correctamente al valor
            action = cmd.get('action')
            print("action", action)
            value = cmd.get('params', {}).get('value')
            print("value", value)
            if value == 0:
                self.stop_device()
            elif value == 1:
                self.start_device()
            elif value == 2:
                self.reset_device()
            print(f"📥 Comando recibido en {topic}: {cmd}")
            self.log(f"📥 Comando recibido en {topic}: {cmd}")
        except Exception as e:
            self.log(f"❌ Error al procesar mensaje: {e}")

    def send_signal(self, topic_info: dir, signal_info: dir):
        topic = f"tenant/{topic_info["organization_id"]}/gateway/{topic_info["gateway_id"]}/device/{topic_info["serial_number"]}/signal"
        self._publish(topic, json.dumps(signal_info))

    def save_device(self, organization_id: str, gateway_id: str, device: dict):
        topic = f"tenant/{organization_id}/gateway/{gateway_id}/device/{device['serialNumber']}/device"
        payload = json.dumps(device)
        self._publish(topic, payload)
        print(topic)
        print(payload)
        self.log(f"▶ Dispositivo {device['serialNumber']} enviado")

    def is_valid_objectid(self, v: str) -> bool:
        try:
            ObjectId(v)
            return True
        except Exception:
            return False

    def send_gateway(self):
        name = "test"
        loc = "test"
        print("self.client", self.client)
        print(self)

        # 2) Preparar datos
        org_id = gateway.get('organizationId')
        gw_id  = gateway.get('gatewayId')
        if not self.is_valid_objectid(gw_id):
            gw_id = str(ObjectId())

        data = {
            "name":           name,
            "organizationId": org_id,
            "location":       loc,
            "gatewayId":      gw_id
        }

        # 3) Construir topic y payload
        topic   = f"tenant/{org_id}/gateway/register/request"
        payload = json.dumps({**data, "timestamp": datetime.utcnow().isoformat()})

        # 4) Publicar y esperar ACK
        info = self.client.publish(topic, payload, qos=1)
        info.wait_for_publish()  # bloquea hasta recibir PUBACK

        # 5) Comprobar resultado
        if info.rc == mqtt.MQTT_ERR_SUCCESS:
            self.log(f"▶ Solicitud de registro enviada a {topic} (mid={info.mid})")
        else:
            self.log(f"❌ Falló publish() rc={info.rc}")



    def request_gateway_config(self, timeout: float = 5.0) -> dict[str, any] | None:
        """
        Publish a gateway-config request over MQTT and wait for the response.

        :param timeout: Maximum seconds to wait for the response.
        :return: Parsed gateway config dict, or None if timed out or on error.
        """
        # Build topics based on current gateway info
        org_id = gateway.get('organizationId')
        gw_id  = gateway.get('gatewayId')
        req_topic  = f"tenant/{org_id}/gateway/{gw_id}/config/request"
        resp_topic = f"tenant/{org_id}/gateway/{gw_id}/config/response"

        response: dict[str, any] = {}
        received = threading.Event()

        # Temporary callback to capture the first response
        def _on_config_response(client, userdata, msg):
            try:
                payload = msg.payload.decode('utf-8')
                response.update(json.loads(payload))
            except Exception:
                pass
            finally:
                received.set()

        # Subscribe and add callback
        self.client.subscribe(resp_topic, qos=1)
        self.client.message_callback_add(resp_topic, _on_config_response)

        # Publish the config request
        payload = json.dumps({"timestamp": time.time()})
        self.client.publish(req_topic, payload, qos=1)
        self.log(f"▶ Gateway config request published to {req_topic}")

        # Wait for response or timeout
        if not received.wait(timeout):
            self.log(f"⚠️ No gateway config received within {timeout}s.")
            result = None
        else:
            result = response

        # Clean up callback
        self.client.message_callback_remove(resp_topic)
        return result


        