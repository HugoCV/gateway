from abc import ABC, abstractmethod
from pymodbus.client import ModbusTcpClient, ModbusSerialClient
import threading, time, os, glob
from serial.rs485 import RS485Settings

class BaseModbusClient(ABC):
    def __init__(self, device, send_signal, log, slave_id, modbus_cfg, signal_group):
        self.device = device
        self.signal_group = signal_group
        self.log = log
        self.send_signal = send_signal
        self.slave_id = slave_id
        self.modbus_cfg = modbus_cfg
        self.modbus_regs = self.modbus_cfg["registers"].items()
        self.addresses = [r["address"] for r in self.modbus_cfg["registers"].values()]
        self.client = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._reconnecting = False
        self.poll_interval = 0.5

    # ---------------------------
    # Life Cicle
    # ---------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            self.log("Thread ya corriendo")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.auto_reconnect, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            if threading.current_thread() != self._thread:
                self._thread.join(timeout=1)
        self.disconnect()

    def auto_reconnect(self, delay=5.0):
        if self._reconnecting:
            return
        self._reconnecting = True
        self.disconnect()
        while not self._stop_event.is_set():
            if self.connect():
                self.device.update_connected()
                self.start_reading()
                break
            self.log(f"Reintentando conexión en {delay}s")
            self._stop_event.wait(delay)
        self._reconnecting = False

    # ---------------------------
    # Abstract Methods
    # ---------------------------
    @abstractmethod
    def connect(self): ...
    @abstractmethod
    def disconnect(self): ...

    # ---------------------------
    # Utilities
    # ---------------------------
    def read_holding_registers(self, address, count=1):
        if not self.client:
            return None
        with self._lock:
            rr = self.client.read_holding_registers(address, count=count, device_id=self.slave_id)
            if rr and not rr.isError():
                return list(rr.registers)
        return None

    def write_register(self, address, value):
        if not self.client:
            return False
        rr = self.client.write_register(address, value, device_id=self.slave_id)
        return rr and not rr.isError()

    def start_reading(self):
        if not self.is_connected():
            return
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def _poll_loop(self):
        while not self._stop_event.is_set():
            regs = {}
            for addr in self.addresses:
                result = self.read_holding_registers(addr)
                if result:
                    regs[addr] = result[0]
            self._read_callback(regs)
            self._stop_event.wait(self.poll_interval)

    def is_connected(self):
        if not self.client:
            return False
        return getattr(self.client, "is_socket_open", lambda: False)() or getattr(self.client, "connected", False)

    def _build_signal_from_regs(self, read_regs):
        """
        Construye un diccionario de señales interpretadas a partir de los registros leídos.
        Soporta mapeos de tipo {'valor': 'texto'} o {'valor': {'value': 'texto', 'kind': 'fault'}}.
        """
        signal = {}

        for key, register in self.modbus_regs:
            addr = register.get("address")
            scale = register.get("scale", 1)
            types = register.get("types", {})
            value = read_regs.get(addr)

            if value is None:
                signal[key] = {"value": None, "kind": "operation"}
                continue

            # aplicar escala numérica
            if scale and isinstance(value, (int, float)):
                value *= scale

            kind = "operation"

            if types:
                mapped = types.get(str(int(value)))  
                if isinstance(mapped, dict):
                    value = mapped.get("value", f"Desconocido({value})")
                    kind = mapped.get("kind", "operation")
                elif isinstance(mapped, str):
                    value = mapped
                else:
                    value = f"Desconocido({value})"

            signal[key] = {"value": value, "kind": kind}

        return signal


    def _read_callback(self, regs):
        payload = self._build_signal_from_regs(regs)
        if payload:
            self.send_signal(payload, self.signal_group)