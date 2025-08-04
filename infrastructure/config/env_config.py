# config/env_config.py

import os
from dotenv import load_dotenv

# Carga el archivo .env si existe
load_dotenv()

# MQTT
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

# RS485
RS485_PORT = os.getenv("RS485_PORT", "")
RS485_BAUDRATE = int(os.getenv("RS485_BAUDRATE", 9600))

# Otros valores opcionales
ENVIRONMENT = os.getenv("ENV", "development")

# Puedes agrupar la configuración si prefieres
MQTT_CONFIG = {
    "host": MQTT_HOST,
    "port": MQTT_PORT,
    "user": MQTT_USER,
    "password": MQTT_PASS,
}

RS485_CONFIG = {
    "port": RS485_PORT,
    "baudrate": RS485_BAUDRATE,
}
