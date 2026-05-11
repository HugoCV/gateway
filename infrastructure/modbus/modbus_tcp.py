import time
import threading
from pymodbus.client import ModbusTcpClient

MODBUS_SCALES = {
    "curr": 0.1,
    "power": 0.1,
    "freqRef": 0.01,
    "freq": 0.01,
}

SIGNAL_MODBUS_TCP_DIR = {
    "freqRef": 5,
    "accTime": 7,
    "decTime": 8,
    "curr": 9,
    "freq": 10,
    "volt": 11,
    "voltDcLink": 12,
    "power": 13,
    "fault": 15,
    "stat": 17,
    "dir": 6,
    "speed": 786,
    "alarm": 816,
    "temp": 861,
}

STATUS_TYPES_DIR = {0: "stop", 1: "fault", 2: "run"}
DIR_TYPE_DIR = {
    1: "stop",
    4: "reverse",
    65: "auto",
    66: "fwd",
    129: "auto",
    130: "fwd",
    193: "auto",
    257: "acc",
    258: "fwd",
}

DEVICE = {
    "status": {"address": 898, "values": {"on": 3, "off": 0, "run": 2}},
    "mode": {"address": 4358, "values": {"local": 2, "remote": 4}},
    "restart": {"address": 901, "values": {"on": 1, "off": 0}},
}


class ModbusTcp:
    def __init__(self, device, send_signal, log, ip, port, slave_id):
        self.ip = ip
        self.port = port
        self.slave_id = slave_id
        self.device = device
        self.send_signal = send_signal
        self.log = log
        self.client: ModbusTcpClient | None = None
        self._lock = threading.Lock()
        self.poll_interval = 0.5

        # Control de hilos
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._reconnecting = False

    def _get_signal_map(self) -> dict[str, int]:
        modbus_config = getattr(self.device, "device", {}).get("modbusConfig")
        if not isinstance(modbus_config, dict):
            return SIGNAL_MODBUS_TCP_DIR

        if modbus_config.get("protocol") != "modbus-tcp":
            return SIGNAL_MODBUS_TCP_DIR

        config_map = modbus_config.get("registers")
        if not isinstance(config_map, dict):
            return SIGNAL_MODBUS_TCP_DIR

        registers: dict[str, int] = {}
        for key, value in config_map.items():
            try:
                address = value.get("address") if isinstance(value, dict) else value
                registers[str(key)] = int(address)
            except (TypeError, ValueError):
                self.log(f"⚠️ Registro TCP inválido para {key}: {value}")

        return registers or SIGNAL_MODBUS_TCP_DIR

    def _get_command(self, name: str):
        modbus_config = getattr(self.device, "device", {}).get("modbusConfig")
        if isinstance(modbus_config, dict) and modbus_config.get("protocol") == "modbus-tcp":
            commands = modbus_config.get("commands")
            if isinstance(commands, dict) and isinstance(commands.get(name), dict):
                return commands[name]
        return DEVICE.get(name)

    def _write_command_value(self, command_name: str, value_name: str) -> bool:
        command = self._get_command(command_name)
        if not isinstance(command, dict):
            self.log(f"⚠️ Comando TCP no configurado: {command_name}")
            return False

        values = command.get("values")
        if not isinstance(values, dict) or value_name not in values:
            self.log(f"⚠️ Valor TCP no configurado: {command_name}.{value_name}")
            return False

        try:
            address = int(command["address"])
            value = int(values[value_name])
        except (KeyError, TypeError, ValueError):
            self.log(f"⚠️ Comando TCP inválido: {command_name}.{value_name}")
            return False

        return self.write_register(address, value)

    # ---------------------------
    # Ciclo de vida
    # ---------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            self.log("⚠️ ModbusTcp: ya hay un hilo corriendo")
            return
        self.log("▶️ START Modbus TCP")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.auto_reconnect, daemon=True)
        self._thread.start()

    def stop(self):
        self.log("⏹️ STOP Modbus TCP")
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            if threading.current_thread() != self._thread:
                self._thread.join(timeout=1)
        self.disconnect()

    # ---------------------------
    # Conexión y reconexión
    # ---------------------------
    def auto_reconnect(self, delay: float = 5.0):
        if self._reconnecting:
            self.log("⚠️ auto_reconnect TCP ya en curso, no se lanza otro")
            return

        self._reconnecting = True
        self.disconnect()
        self.log("🔄 Iniciando auto_reconnect TCP...")

        while not self._stop_event.is_set():
            if self.connect():
                self.log("✅ Conexión establecida a Modbus TCP")
                self.device.update_connected()
                self.start_reading()
                break
            self.log(f"❌ Falló conexión TCP, reintento en {delay}s")
            self._stop_event.wait(delay)

        self._reconnecting = False

    def connect(self) -> bool:
        self.log(f"Iniciando conexión Modbus TCP a {self.ip}:{self.port}")
        try:
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None

            self.client = ModbusTcpClient(
                host=self.ip, port=self.port, timeout=1.0, retries=0
            )
            if not self.client.connect():
                self.log(f"❌ No se pudo conectar a {self.ip}:{self.port}")
                self.client = None
                return False

            self.log("✅ Se conectó por medio de TCP")
            return True
        except Exception as e:
            self.log(f"❌ Error conectando a {self.ip}:{self.port}: {e}")
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
            self.client = None
            return False

    def disconnect(self):
        if self.client:
            try:
                self.client.close()
                self.log("⚠️ Modbus TCP disconnected")
            except Exception as e:
                self.log(f"❌ Error durante disconnect: {e}")
            finally:
                self.client = None

    # ---------------------------
    # Polling de registros
    # ---------------------------
    def start_reading(self):
        if not self.is_connected():
            return
        signal_map = self._get_signal_map()
        addrs = list(dict.fromkeys(signal_map.values()))
        self.tcp_poll = self.poll_registers(addresses=addrs, interval=self.poll_interval)

    def poll_registers(self, addresses: list[int], interval: float = 0.5):
        def _poll():
            failure_count = 0
            while not self._stop_event.is_set():
                regs_group = {}
                for addr in addresses:
                    try:
                        regs = self.read_holding_registers(addr, count=1)
                        if regs is not None:
                            regs_group[addr] = regs[0]
                            failure_count = 0
                        else:
                            failure_count += 1
                    except Exception as e:
                        self.log(f"❌ Exception polling register {addr}: {e}")
                        failure_count += 1

                if failure_count >= 3:
                    self.log("⚠️ Modbus TCP parece desconectado")
                    self.device.update_connected()
                    self.start()  # relanza auto_reconnect
                    return

                self._stop_event.wait(interval)
                self._read_callback(regs_group)

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
            self.log("⚠️ Client not connected. Call connect() first.")
            return None
        with self._lock:
            self.log(f"address: {address}")
            self.log(f"count: {count}")
            try:
                rr = self.client.read_holding_registers(address, count=count)
                if rr and not rr.isError():
                    return list(rr.registers)
                self.log(f"❌ Error reading registers: {rr}")
            except Exception as e:
                self.log(f"❌ Exception reading registers: {e}")
        return None

    def write_register(self, address: int, value: int) -> bool:
        if not self.client:
            self.log("⚠️ Client not connected")
            return False
        try:
            rr = self.client.write_register(address, value, device_id=self.slave_id)
            if rr and not rr.isError():
                self.log(f"✍️ TCP escribió en registro {address} = {value}")
                return True
            self.log(f"❌ Error writing register {address}: {rr}")
        except Exception as e:
            self.log(f"❌ Exception writing register {address}: {e}")
        return False

    def update_config(self, ip=None, port=None, slave_id=None):
        changed = False
        if ip and ip != self.ip:
            self.ip = ip
            changed = True
        if port and port != self.port:
            self.port = port
            changed = True
        if slave_id and slave_id != self.slave_id:
            self.slave_id = slave_id
            changed = True

        if changed:
            self.log(f"🔄 Updating TCP config: {self.ip}:{self.port}, slave={self.slave_id}")
            self.stop()
            self.start()
            return True
        return False

    # ---------------------------
    # Comandos
    # ---------------------------
    def turn_on(self) -> bool:
        self.set_remote()
        return self._write_command_value("status", "on")

    def turn_off(self) -> bool:
        self.set_remote()
        is_turned_off = self._write_command_value("status", "off")
        self.set_local()
        return is_turned_off

    def restart(self):
        if not self.client:
            return False
        ok = self._write_command_value("restart", "on")
        self._write_command_value("restart", "off")
        if not self._write_command_value("status", "run"):
            self.turn_on()
        self.log("✔ Comando enviado: RESET")
        return ok

    def set_local(self) -> bool:
        ok = self._write_command_value("mode", "local")
        self.log("✅ Puesto en local" if ok else "❌ No se pudo poner en local")
        return ok

    def set_remote(self) -> bool:
        ok = self._write_command_value("mode", "remote")
        self.log("✅ Puesto en remoto" if ok else "❌ No se pudo poner en remoto")
        return ok

    # ---------------------------
    # Señales
    # ---------------------------
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
                s[name] = {
                    "value": STATUS_TYPES_DIR.get(v, f"Desconocido ({v})"),
                    "kind": "operation",
                }
            if name == "dir":
                s[name] = {
                    "value": DIR_TYPE_DIR.get(v, f"Desconocido ({v})"),
                    "kind": "operation",
                }
        return s

    def _read_callback(self, regs):
        signal = self._build_signal_from_regs(regs, self._get_signal_map())
        payload = {k: v for k, v in signal.items() if v is not None}
        if payload:
            self.send_signal(payload, "drive")
