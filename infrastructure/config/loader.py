# config/loader.py
import os
import json
from dotenv import load_dotenv, find_dotenv

# === Paths ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "../..", "data")

DEVICES_FILE = os.path.join(DATA_DIR, "devices.json")
SIGNALS_FILE = os.path.join(DATA_DIR, "signals.json")
GATEWAY_FILE = os.path.join(DATA_DIR, "gateway.json")


# === Internal caches for lazy loading ===
_gateway_cache = None


# -----------------------------
# Environment & Config Loading
# -----------------------------
def load_env():
    """Load environment variables from .env file if available."""
    dotenv_path = find_dotenv()
    if dotenv_path:
        load_dotenv(dotenv_path)
        print(f"✅ Environment loaded from {dotenv_path}")
    else:
        print("⚠️ No .env file found. Using existing environment variables.")


def load_config():
    """Load and return global configuration (MQTT and RS485) from environment variables."""
    load_env()
    return {
        "MQTT_HOST": os.getenv("MQTT_HOST", "localhost"),
        "MQTT_PORT": int(os.getenv("MQTT_PORT", "1883")),
        "MQTT_USER": os.getenv("MQTT_USER", ""),
        "MQTT_PASS": os.getenv("MQTT_PASS", ""),
        "PORT": os.getenv("RS485_PORT", ""), 
        "BAUDRATE": int(os.getenv("RS485_BAUD", "9600")),
    }


def get_mqtt_config():
    """Return only the MQTT configuration part."""
    cfg = load_config()
    return {
        "MQTT_HOST": cfg["MQTT_HOST"],
        "MQTT_PORT": cfg["MQTT_PORT"],
        "MQTT_USER": cfg["MQTT_USER"],
        "MQTT_PASS": cfg["MQTT_PASS"],
    }


# -----------------------------
# JSON Utility
# -----------------------------
def _load_json(path: str, default):
    """Load JSON from a file. Return default if file not found or invalid."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path: str, data):
    """Save JSON to a file, creating directories if necessary."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"💾 Saved data to {path}")


# -----------------------------
# Gateway
# -----------------------------
def get_gateway():
    """Return a copy of gateway configuration (lazy-loaded from gateway.json)."""
    global _gateway_cache
    if _gateway_cache is None:
        _gateway_cache = _load_json(GATEWAY_FILE, {})
    return dict(_gateway_cache)


def save_gateway(gateway_data: dict):
    """Save gateway configuration to gateway.json and update cache."""
    global _gateway_cache
    _save_json(GATEWAY_FILE, gateway_data)
    _gateway_cache = dict(gateway_data)
