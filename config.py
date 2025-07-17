import os
import json
from dotenv import load_dotenv, find_dotenv

# Rutas
BASE_DIR     = os.path.dirname(__file__)
DATA_DIR     = os.path.join(BASE_DIR, "data")
CONFIG_FILE  = os.path.join(DATA_DIR, "gateway_config.json")
SIGNALS_FILE = os.path.join(DATA_DIR, "signals.json")
DEVICES_FILE = os.path.join(DATA_DIR, "devices.json")
GATEWAY_FILE = os.path.join(DATA_DIR, "gateway.json")

# Variables privadas para lazy loading
_signals = None
_devices = None
_gateway = None


def _load_env():
    """Carga variables de entorno desde .env si existe"""
    dotenv_path = find_dotenv()
    if dotenv_path:
        print(f"🔍 Cargando variables de entorno desde {dotenv_path}")
        load_dotenv(dotenv_path)
    else:
        print("⚠️ .env no encontrado, usando valores por defecto o ya cargados.")


def _load_json(path, default):
    """Carga un archivo JSON y retorna `default` si falla"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def load_config():
    """Carga variables de entorno y datos de configuración: MQTT, gateway, devices, signals"""
    _load_env()

    mqtt_cfg = {
        "MQTT_HOST": os.getenv("MQTT_HOST"),
        "MQTT_PORT": int(os.getenv("MQTT_PORT", "1883")),
        "MQTT_USER": os.getenv("MQTT_USER"),
        "MQTT_PASS": os.getenv("MQTT_PASS"),
    }

    return mqtt_cfg


def get_mqtt_config():
    """Retorna copia de la configuración MQTT"""
    mqtt_cfg, _, _, _ = load_config()
    return dict(mqtt_cfg)


def get_signals():
    """Retorna copia de la lista de señales cargadas (lazy load)"""
    global _signals
    if _signals is None:
        _signals = _load_json(SIGNALS_FILE, [])
    return list(_signals)


def get_devices():
    """Retorna copia de la lista de dispositivos cargados (lazy load)"""
    global _devices
    if _devices is None:
        _devices = _load_json(DEVICES_FILE, [])
    return list(_devices)


def get_gateway():
    """Retorna copia de la configuración del gateway cargada (lazy load)"""
    global _gateway
    print("_gateway", _gateway)
    if _gateway is None:
        _gateway = _load_json(GATEWAY_FILE, {})
    return dict(_gateway)


def save_data(data, file_type):
    """Guarda datos en el archivo correspondiente según file_type."""
    file_map = {
        "config": CONFIG_FILE,
        "signals": SIGNALS_FILE,
        "devices": DEVICES_FILE,
        "gateway": GATEWAY_FILE,
    }
    path = file_map.get(file_type)
    if not path:
        raise ValueError(f"Unknown file_type '{file_type}'")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"💾 '{file_type}' guardado en {path}")
    except Exception as e:
        print(f"❌ Error guardando '{file_type}' en {path}: {e}")

def save_devices(device):
    """Agrega o actualiza un dispositivo en devices.json y actualiza cache"""
    global device_list
    # Carga la lista existente
    items = _load_json(DEVICES_FILE, [])
    updated = False
    for idx, item in enumerate(items):
        if item.get("serialNumber") == device.get("serialNumber"):
            items[idx] = device
            updated = True
            break
    if not updated:
        items.append(device)

    # Guarda en disco
    os.makedirs(os.path.dirname(DEVICES_FILE), exist_ok=True)
    with open(DEVICES_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

    # Actualiza cache local
    device_list = items


def save_gateway(config):
    """Guarda configuración del gateway en gateway.json"""
    os.makedirs(os.path.dirname(GATEWAY_FILE), exist_ok=True)
    with open(GATEWAY_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
