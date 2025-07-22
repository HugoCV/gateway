import os
import json
import platform
import threading
import time
from dotenv import load_dotenv, find_dotenv
import serial
from serial.rs485 import RS485Settings
from pymodbus.client import ModbusSerialClient, ModbusTcpClient
import snap7


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
_serial_port = None


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

    cfg = {
        "MQTT_HOST": os.getenv("MQTT_HOST"),
        "MQTT_PORT": int(os.getenv("MQTT_PORT", "1883")),
        "MQTT_USER": os.getenv("MQTT_USER"),
        "MQTT_PASS": os.getenv("MQTT_PASS"),
        "PORT": os.getenv("RS485_PORT"), 
        "BAUDRATE": int(os.getenv("RS485_BAUD", "9600")),
    }

    return cfg


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

def get_rs485_config():
    """Retorna copia de la configuración RS-485"""
    cfg = load_config()
    return dict(cfg)


def open_rs485():
    """Abre y configura el puerto RS-485 según configuración"""
    global _serial_port
    if _serial_port:
        return _serial_port

    cfg = get_rs485_config()
    port = cfg.get('PORT')  # Lee RS485_PORT desde .env
    baud = cfg.get('BAUDRATE', 9600)
    if not port:
        raise ValueError("RS485_PORT no está configurado en el entorno (.env)")

    # Validación para Windows
    if platform.system() == "Windows" and port.startswith("/dev/"):
        print(f"⚠️ Advertencia: puerto {port} no es estándar en Windows. "
              "Asegúrate de usar algo como 'COM3' en RS485_PORT. Intentando abrir de todos modos...")

    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1
        )
        # Configuración RS-485: control automático de dirección vía RTS
        ser.rs485_mode = RS485Settings(
            rts_level_for_tx=True,
            rts_level_for_rx=False,
            delay_before_tx=None,  # Usar None según la librería
            delay_before_rx=None   # Usar None según la librería
        )
        _serial_port = ser
        print(f"🔌 RS-485 abierto en {port} a {baud}bps")
    except Exception as e:
        print(f"❌ No se pudo abrir RS-485 en {port}: {e}")
        _serial_port = None
    return _serial_port



def read_rs485(num_bytes=400010):
    """
    Lee `num_bytes` bytes del dispositivo RS-485.
    Valida que num_bytes sea un entero > 0, abre (o reutiliza) el puerto y devuelve los datos leídos.
    """
    # 1. Validar el parámetro
    try:
        n = int(num_bytes)
        if n <= 0:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError(f"read_rs485: num_bytes inválido ({num_bytes!r}), debe ser un entero > 0")

    # 2. Abrir o reutilizar el puerto
    ser = open_rs485()

    # 3. Leer y manejar errores
    try:
        data = ser.readline(n)
        data2 = ser.read(n)
        print("num_bytes", num_bytes)
        print("data", data)
        print("data2", data2)
        if not data:
            print("⚠️ No se recibieron datos del RS-485.")
        else:
            print(f"Leídos {len(data)} bytes: {data!r}")
        return data
    except Exception as e:
        print(f"❌ Error leyendo RS-485: {e}")
        raise
def start_continuous_read_in_thread(*args, **kwargs):
    """
    Arranca continuous_read_register en un hilo demonio,
    para no bloquear el mainloop de Tkinter.
    """
    t = threading.Thread(target=continuous_read_register, args=args, kwargs=kwargs)
    t.daemon = True
    t.start()
    return t

def read_register(slave_id, reg_address, port="COM3", baud=9600, timeout=1):
    client = ModbusSerialClient(
        port='COM3',
        baudrate=9600,
        timeout=4
    )
    if not client.connect():
        raise ConnectionError("No fue posible abrir el puerto RS‑485")
    # Lee 1 registro (2 bytes) en la dirección reg_address
    rr = client.read_holding_registers(
        address=10,  # posición 1
        count=2,               # debe ir por nombre
        slave=1         # idem
    )

    client.close()
    if rr.isError():
        raise IOError(f"Error en lectura Modbus: {rr}")
    # rr.registers es una lista de enteros
    print("registro", rr.registers[0])
    return rr.registers[0]

def continuous_read_register(slave_id=1,
                             reg_address=10,
                             port="COM3",
                             baud=9600,
                             timeout=4,
                             count=1,
                             interval=1.0,
                             callback=None):
    """
    Lee continuamente `count` registros comenzando en `reg_address`
    del esclavo `slave_id` por RS‑485, imprimiendo su valor cada
    `interval` segundos.
    """
    client = ModbusSerialClient(
        port=port,
        baudrate=baud,
        timeout=timeout,
        bytesize=8,
        parity='N',
        stopbits=1
    )
    if not client.connect():
        raise ConnectionError(f"No fue posible abrir el puerto {port}")

    try:
        print(f"▶ Iniciando lectura continua: esclavo={slave_id}, addr={reg_address}, count={count}")
        while True:
            rr = client.read_holding_registers(
                address=reg_address,
                count=count,
                slave=slave_id
            )
            if rr.isError():
                print(f"❌ Error en lectura Modbus: {rr}")
            else:
                for i, val in enumerate(rr.registers):
                    callback(val)
                    #print(f"Registro {reg_address + i} = {val}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("⏹ Lectura continua detenida por el usuario")
    finally:
        client.close()
        print("🔌 Conexión Modbus cerrada")
def start_continuous_read_in_thread(*args, callback=None, **kwargs):
    """
    Arranca continuous_read_register en un hilo demonio,
    para no bloquear el mainloop de Tkinter.
    """
    t = threading.Thread(target=continuous_read_register, args=args, kwargs={**kwargs, "callback": callback})
    t.daemon = True
    t.start()
    return t

def write_rs485(data: bytes):
    """Envía bytes al dispositivo RS-485"""
    ser = open_rs485()
    ser.write(data)

def write_registers(slave_id, reg_address, values, port="COM3", baud=9600, timeout=1):
    """
    Escribe uno o varios registros en un esclavo Modbus.

    :param slave_id: ID del dispositivo esclavo (int)
    :param reg_address: Dirección inicial del registro (int)
    :param values: Valor único (int) o lista de valores a escribir ([int, int, ...])
    :param port: Puerto serie (str), p.ej. "COM3"
    :param baud: Baudrate de la conexión (int)
    :param timeout: Tiempo de espera en segundos (int)
    :return: El objeto respuesta del write; lanzar excepción si hay error.
    """
    client = ModbusSerialClient(
        port=port,
        baudrate=baud,
        timeout=timeout,
        bytesize=8,
        parity='N',
        stopbits=1
    )
    if not client.connect():
        raise ConnectionError(f"No fue posible abrir el puerto RS‑485 ({port})")

    # Decide si es un único registro o varios
    if isinstance(values, list):
        rq = client.write_registers(address=reg_address, values=values, salve=slave_id)
    else:
        rq = client.write_register(address=reg_address, value=values, slave=slave_id)

    client.close()

    if rq.isError():
        raise IOError(f"Error al escribir registro(s): {rq}")

    # Muestra información de la escritura
    if isinstance(values, list):
        print(f"Escritura exitosa: registros {reg_address} a {reg_address + len(values) - 1} = {values}")
    else:
        print(f"Escritura exitosa: registro {reg_address} = {values}")

    return rq

import requests

def connect_http():
    url = "http://125.100.1.19/api/dashboard/drive/stat"
    try:
        response = requests.get(url, auth=('Admin', '0'), timeout=5)
        print(f"🔎 Status code: {response.status_code}")
        response.raise_for_status()
        print("✅ Respuesta OK")
        print(response.text[:500])  # muestra solo los primeros 500 caracteres
    except requests.exceptions.Timeout:
        print("⏳ Tiempo de espera agotado (timeout)")
    except requests.exceptions.HTTPError as e:
        print(f"⚠️ Error HTTP: {e}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Error al conectar: {e}")

def connect_logo2():

    client = snap7.client.Client()
    client.connect('125.100.1.20', 0, 2)  # IP, rack, slot (LOGO!: 0,1)
    data = client.read_area(snap7.types.Areas.MK, 0, 0, 10)  # lee 10 bytes de marcas
    print(data)
    client.disconnect()

def connect_logo():
    client = ModbusTcpClient('125.100.1.20', port=502)
    client.connect()

    # Usar solo argumentos nombrados
    rr = client.write_register(address=1, value=123, slave=1)

    if not rr.isError():
        print("✅ Registros escritors:", rr)
    else:
        print("⚠️ Error al leer:", rr)

    client.close()
