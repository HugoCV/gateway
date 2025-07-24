# drivers/rs485.py
import serial
from serial.rs485 import RS485Settings
import platform

_serial_port = None

def open_rs485(port, baud):
    global _serial_port
    if _serial_port:
        return _serial_port
    if platform.system() == "Windows" and port.startswith("/dev/"):
        print(f"⚠️ Port {port} not standard on Windows")

    ser = serial.Serial(port=port, baudrate=baud, timeout=1)
    ser.rs485_mode = RS485Settings(rts_level_for_tx=True, rts_level_for_rx=False)
    _serial_port = ser
    return ser

def read_rs485(num_bytes):
    ser = _serial_port or open_rs485()
    return ser.read(num_bytes)

def write_rs485(data: bytes):
    ser = _serial_port or open_rs485()
    ser.write(data)
