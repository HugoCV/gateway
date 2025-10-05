import threading
import time
import os
import glob
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from serial.rs485 import RS485Settings

MODBUS_SCALES = {
    "curr": 0.1,      # /10
    "power": 0.1,     # /10
    "freqRef": 0.01,  # /100
    "freq": 0.01,     # /100
}

SIGNAL_MODBUS_SERIAL_DIR = {
    "freqRef": 4,
    "accTime": 6,
    "decTime": 7,
    "curr": 8,
    "freq": 9,
    "volt": 10,
    "power": 12,
    "stat": 16,
    "dir": 5,       
    "speed": 785,
    "alarm": 815,
    "temp": 859,
}

DEVICE = {
    "status": {
        "address": 897,
        "values": {"on": 3, "off": 0}
    },
    "mode": {
        "address": 4357,
        "values": {"local": 2, "remote": 3}
    }
}

STATUS_TYPES_DIR = {0: "stop", 1: "fault", 2: "run", 7:"run"}
DIR_TYPE_DIR = {4: "reverse", 1: "stop", 129: "auto", 130: "fwd", 193: "acc", 194: "fwd", 66:"fwd"}


class ModbusSerial:
    """
    Manages a Modbus RTU connection over a serial port (RS-485).
    """
    def __init__(self, device, send_signal, log, port, baudrate, slave_id):
        self.device = device
        self.log = log
        self.send_signal = send_signal
        self.client: ModbusSerialClient | None = None
        self._lock = threading.Lock()
        self.poll_interval = 0.5
        self.port = port
        self.baudrate = baudrate
        self.slave_id = slave_id

        # Control de hilos
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._reconnecting = False

    # ---------------------------
    # Ciclo de vida
    # ---------------------------
    def start(self):
        """Inicia el hilo de auto_reconnect si no está corriendo."""
        if self._thread and self._thread.is_alive():
            self.log("⚠️ ModbusSerial: ya hay un hilo corriendo")
            return
        self.log("▶️ START Modbus Serial")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.auto_reconnect, daemon=True)
        self._thread.start()

    def stop(self):
        """Detiene el loop de reconnect y cierra la conexión."""
        self.log("⏹️ STOP Modbus Serial")
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            if threading.current_thread() != self._thread:  # evita self-join
                self._thread.join(timeout=1)
        self.disconnect()

    def auto_reconnect(self, delay=5.0):
        """Loop de reconexión automática."""
        if self._reconnecting:
            self.log("⚠️ auto_reconnect ya en curso, no se lanza otro")
            return

        self._reconnecting = True
        self.disconnect()
        self.log("🔄 Iniciando auto_reconnect...")

        while not self._stop_event.is_set():
            if self.connect():
                self.log("✅ Conexión Modbus Serial establecida")
                self.device.update_connected()
                self.start_reading()
                break
            self.log(f"❌ Falló conexión Modbus Serial. Reintento en {delay}s")
            self._stop_event.wait(delay)

        self._reconnecting = False

    # ---------------------------
    # Conexión
    # ---------------------------
    def connect(self, timeout: float = 1.0) -> bool:
        """Abre la conexión Modbus RTU sobre un puerto serie."""
        try:
            available_ports = glob.glob(self.port)
            if not available_ports:
                self.log("⚠️ No se encontraron puertos disponibles")
                return False

            connect_port = available_ports[0]
            if not os.path.exists(connect_port):
                self.log(f"⚠️ Puerto serie {connect_port} no encontrado")
                return False

            self.client = ModbusSerialClient(
                port=connect_port,
                baudrate=self.baudrate,
                parity="N",
                stopbits=1,
                bytesize=8,
                timeout=timeout,
                retries=0,
            )
            connected = self.client.connect()
            if connected:
                try:
                    transport = getattr(self.client, 'socket', None)
                    if hasattr(transport, 'rs485_mode'):
                        transport.rs485_mode = RS485Settings(
                            rts_level_for_tx=True,
                            rts_level_for_rx=False,
                            delay_before_tx=None,
                            delay_before_rx=None
                        )
                except Exception as e:
                    self.log(f"RS-485 mode no soportado: {e}")

                self.log(f"Conectado a {self.port}@{self.baudrate} (slave={self.slave_id})")
            else:
                self.log(f"❌ Falló conexión en {self.port}@{self.baudrate}")
            return connected

        except ModbusException as e:
            self.log(f"❌ Modbus exception: {e}")
            return False
        except Exception as e:
            self.log(f"❌ Error inesperado en connect: {e}")
            return False

    def disconnect(self):
        """Cierra la conexión Modbus/serial."""
        if self.client:
            try:
                self.client.close()
                self.log("⚠️ Modbus RTU disconnected")
            except Exception as e:
                self.log(f"❌ Error al desconectar: {e}")
            finally:
                self.client = None

    # ---------------------------
    # Polling de registros
    # ---------------------------
    def poll_registers(self, addresses: list[int], interval: float = 0.5):
        def _poll():
            failure_count = 0
            while not self._stop_event.is_set():
                regs_group = {}
                for addr in addresses:
                    try:
                        regs = self.read_holding_registers(addr, count=1)
                        if regs:
                            regs_group[addr] = regs[0]
                            failure_count = 0
                        else:
                            failure_count += 1
                    except Exception as e:
                        self.log(f"❌ Error polling {addr}: {e}")
                        failure_count += 1

                if failure_count >= 3:
                    self.log("⚠️ Modbus serial parece desconectado")
                    self.device.update_connected()
                    self.start()  # relanza auto_reconnect
                    return

                self._stop_event.wait(interval)
                self.on_modbus_serial_read_callback(regs_group)

        thread = threading.Thread(target=_poll, daemon=True)
        thread.start()
        return thread

    # ---------------------------
    # Utilidades
    # ---------------------------
    def is_connected(self) -> bool:
        if not self.client:
            return False
        try:
            if hasattr(self.client, "is_socket_open"):
                return self.client.is_socket_open()
            return getattr(self.client, "connected", False)
        except Exception:
            return False

    def read_holding_registers(self, address: int, count: int = 1):
        if not self.client:
            self.log("⚠️ Client not connected")
            return None
        with self._lock:
            try:
                rr = self.client.read_holding_registers(address, count=count, device_id=self.slave_id)
                if rr and not rr.isError():
                    return list(rr.registers)
                self.log(f"❌ Error en read_holding_registers: {rr}")
            except Exception as e:
                self.log(f"❌ Excepción en read_holding_registers: {e}")
        return None

    def write_register(self, address: int, value: int) -> bool:
        if not self.client:
            self.log("⚠️ Client not connected")
            return False
        try:
            rr = self.client.write_register(address, value, device_id=self.slave_id)
            if rr and not rr.isError():
                self.log(f"✍️ Escribió {value} en registro {address}")
                return True
            self.log(f"❌ Error writing register {address}: {rr}")
        except Exception as e:
            self.log(f"❌ Excepción writing register {address}: {e}")
        return False

    def restart(self):
        self.write_register(900, 1)
        self.write_register(900, 0)
        self.turn_on()

    def turn_on(self) -> bool:
        return self.write_register(DEVICE["status"]["address"], DEVICE["status"]["values"]["on"])

    def turn_off(self) -> bool:
        return self.write_register(DEVICE["status"]["address"], DEVICE["status"]["values"]["off"])

    def _build_signal_from_regs(self, regs: dict[int, int], modbus_dir) -> dict:
        s = {}
        for name, addr in modbus_dir.items():
            v = regs.get(addr)
            if v is None:
                s[name] = None
                continue
            if name in MODBUS_SCALES:
                s[name] = {"value": v * MODBUS_SCALES[name], "kind": "operation"}
            else:
                s[name] = {"value": v, "kind": "operation"}
            if name == "stat":
                s[name] = {"value": STATUS_TYPES_DIR.get(v, f"Desconocido ({v})"), "kind": "operation"}
            if name == "dir":
                s[name] = {"value": DIR_TYPE_DIR.get(v, f"Desconocido ({v})"), "kind": "operation"}
        return s

    def set_local(self) -> bool:
        ok = self.write_register(DEVICE["mode"]["address"], DEVICE["mode"]["values"]["local"])
        self.log("✅ Puesto en local" if ok else "❌ No se pudo poner en local")
        return ok

    def set_remote(self) -> bool:
        ok = self.write_register(DEVICE["mode"]["address"], DEVICE["mode"]["values"]["remote"])
        self.log("✅ Puesto en remoto" if ok else "❌ No se pudo poner en remoto")
        return ok

    def start_reading(self):
        if not self.is_connected():
            return
        addrs = list(dict.fromkeys(SIGNAL_MODBUS_SERIAL_DIR.values()))
        self.serial_poll = self.poll_registers(addresses=addrs, interval=self.poll_interval)

    def on_modbus_serial_read_callback(self, regs):
        signal = self._build_signal_from_regs(regs, SIGNAL_MODBUS_SERIAL_DIR)
        payload = {k: v for k, v in signal.items() if v is not None}
        if payload:
            self.send_signal(payload, "drive")
    def update_config(self, port=None, baudrate=None, slave_id=None) -> bool:
        """Update TCP parameters and reconnect if needed."""
        changed = False

        if port and port != self.port:
            self.port = port
            changed = True

        if baudrate and baudrate != self.baudrate:
            self.baudrate = baudrate
            changed = True

        if slave_id and slave_id != self.slave_id:
            self.slave_id = slave_id
            changed = True

        if changed:
            self.log(f"🔄 Updating TCP config: {self.baudrate}:{self.port}, slave={self.slave_id}")
            self.stop_reconnect()
            self.start()
            return True

        return False
