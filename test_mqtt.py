# test_mqtt_cb.py
import time, json, threading, uuid
from paho.mqtt import client as mqtt
import ssl, certifi

# --- Credenciales / host (las tuyas) ---
MQTT_HOST = "rf1225b9.ala.us-east-1.emqxsl.com"
MQTT_PORT = 8883
MQTT_USER = "alrotek"
MQTT_PASS = "test"

ORG_ID = "68784d9492ad8045bc7b167a"
GW_ID  = "68784d9592ad8045bc7b16ad"

def make_client(cid: str):
    c = mqtt.Client(client_id=cid, protocol=mqtt.MQTTv311)
    c.username_pw_set(MQTT_USER, MQTT_PASS)
    c.tls_set(ca_certs=certifi.where(), cert_reqs=ssl.CERT_REQUIRED)
    return c

# -----------------------------
# 1) Echo con callback
# -----------------------------
def echo_selftest_cb(callback):
    """Suscribe a un tópico random y publica en el mismo. Llama 'callback(topic, payload_str)'. """
    topic = f"selftest/{uuid.uuid4().hex}"
    connected = threading.Event()
    got_msg   = threading.Event()

    def on_connect(c,u,f,rc,props=None):
        print(f"[ECHO] on_connect rc={rc}")
        if rc == 0: connected.set()

    def on_message(c,u,m):
        payload = m.payload.decode("utf-8", "ignore")
        print(f"[ECHO] RX {m.topic}: {payload}")
        try:
            callback(m.topic, payload)
        finally:
            got_msg.set()

    cl = make_client(f"echo-{uuid.uuid4().hex[:6]}")
    cl.on_connect = on_connect
    cl.on_message = on_message

    print(f"[ECHO] connect {MQTT_HOST}:{MQTT_PORT}")
    cl.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    cl.loop_start()
    if not connected.wait(5):
        print("[ECHO] ❌ sin CONNECT"); cl.loop_stop(); cl.disconnect(); return False

    print(f"[ECHO] SUB {topic}")
    cl.subscribe(topic, qos=0)

    msg = "ping"
    print(f"[ECHO] PUB → {topic}: {msg}")
    cl.publish(topic, msg, qos=0)

    ok = got_msg.wait(5)
    print(f"[ECHO] RESULT ok={ok}")
    cl.loop_stop(); cl.disconnect()
    return ok

# ---------------------------------------
# 2) Gateway config con callback
# ---------------------------------------
def gateway_test_cb(callback, timeout=7.0):
    """
    Suscribe a .../config/response y publica en .../config/request.
    Llama 'callback(data_dict, msg)' cuando llega la respuesta.
    """
    RESP = f"tenant/{ORG_ID}/gateway/{GW_ID}/config/response"
    REQ  = f"tenant/{ORG_ID}/gateway/{GW_ID}/config/request"

    connected = threading.Event()
    got_resp  = threading.Event()

    def on_connect(c,u,f,rc,props=None):
        print(f"[GW] on_connect rc={rc}")
        if rc == 0: connected.set()

    def on_resp(c,u,m):
        print(f"[GW] RX topic={m.topic} bytes={len(m.payload)}")
        try:
            data = json.loads(m.payload.decode("utf-8"))
            print(data)
        except Exception as e:
            print("[GW] json err:", e); return
        try:
            callback(data, m)   # <-- tu callback
        finally:
            got_resp.set()

    cl = make_client(f"gwcb-{uuid.uuid4().hex[:6]}")
    cl.on_connect = on_connect

    print(f"[GW] connect {MQTT_HOST}:{MQTT_PORT}")
    cl.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    cl.loop_start()
    if not connected.wait(5):
        print("[GW] ❌ sin CONNECT"); cl.loop_stop(); cl.disconnect(); return None

    # Usamos message_callback_add para solo ese tópico
    cl.message_callback_add(RESP, on_resp)
    print(f"[GW] SUB {RESP}")
    cl.subscribe(RESP, qos=1)

    payload = json.dumps({"timestamp": time.time()})
    print(f"[GW] PUB → {REQ}")
    cl.publish(REQ, payload, qos=1)

    ok = got_resp.wait(timeout)
    print(f"[GW] RESULT ok={ok}")

    cl.message_callback_remove(RESP)
    cl.loop_stop(); cl.disconnect()
    return ok

# -----------------------------
# Ejemplo de uso de callbacks
# -----------------------------
def my_echo_cb(topic, payload_str):
    print(f"[CB] echo callback: {topic=} {payload_str=}")

def my_gateway_cb(data_dict, msg):
    print(f"[CB] gateway callback keys={list(data_dict.keys())}")

if __name__ == "__main__":
    print("=== TEST 1: Echo con callback ===")
    echo_ok = echo_selftest_cb(my_echo_cb)

    print("\n=== TEST 2: Gateway con callback ===")
    gw_ok = gateway_test_cb(my_gateway_cb)

    print("\n=== SUMMARY ===")
    print("Echo OK:", echo_ok)
    print("Gateway OK:", gw_ok)
