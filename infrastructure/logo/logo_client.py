# drivers/logo_modbus.py
import threading
import time
from pymodbus.client import ModbusTcpClient

SIGNAL_LOGO_DIR = {
    "status": 0,
    "restartTime": 1,
    "voltageResetTime": 2,
    "autoResetTime": 4,
    "workHours": 5,
    "workMinutes": 6,
    "lowLevelResetTime": 8,
    "highPressureCount": 11,
    "networkPressure": 16,
    "dischargePressure": 17,
}

LOGO_COMMANDS = {
    "turnOn": {"address": 3, "values": {"on": 1}},
    "turnOff": {"address": 4, "values": {"on": 1}},
    "restart": {"address": 5, "values": {"on": 1}},
}

LOGO_STATUS_TYPES = {
    0: {"value": "Panel desenergizado", "kind": "operation"},
    1: {"value": "Falla de voltaje", "kind": "fault"},
    3: {"value": "Falla de voltaje", "kind": "fault"},
    8: {"value": "Reiniciando", "kind": "operation"},
    9: {"value": "Falla de voltaje", "kind": "fault"},
    32: {"value": "Falla: bajo nivel", "kind": "fault"},
    33: {"value": "Selector Fuera", "kind": "operation"},
    34: {"value": "Falla: bajo nivel", "kind": "fault"},
    35: {"value": "Apagado por selector", "kind": "operation"},
    41: {"value": "Falla térmica/variador", "kind": "fault"},
    97: {"value": "Alta presión (conteo)", "kind": "operation"},
    161: {
        "value": "Arranque fallido (LOGO envía señal, contactor/variador no encienden)",
        "kind": "fault",
    },
    163: {"value": "Operando", "kind": "operation"},
    512: {"value": "Logo reiniciando", "kind": "operation"},
    513: {"value": "Falla de voltaje", "kind": "fault"},
    520: {"value": "Reiniciando", "kind": "operation"},
    521: {"value": "Falla de voltaje", "kind": "fault"},
    544: {"value": "Falla de bajo nivel", "kind": "fault"},
    545: {"value": "Reposo", "kind": "operation"},
    546: {"value": "Falla de bajo nivel", "kind": "fault"},
    547: {"value": "Desaceleracion", "kind": "operation"},
    577: {"value": "Falla de voltaje", "kind": "fault"},
    608: {"value": "Falla bajo nivel", "kind": "fault"},
    609: {"value": "Paro por alta precion", "kind": "operation"},
    611: {"value": "Desaceleracion", "kind": "operation"},
    673: {"value": "Encendido por selector", "kind": "operation"},
    675: {"value": "Operacion", "kind": "operation"},
    737: {"value": "Aceleracion", "kind": "operation"},
    739: {"value": "Operacion", "kind": "operation"},
    1569: {"value": "Falla de confirma", "kind": "fault"},
    1633: {"value": "Falla de confirma", "kind": "fault"},
    4705: {"value": "En Transito", "kind": "operation"},
    4707: {"value": "Desaceleracion", "kind": "operation"},
}


class LogoModbusClient:
    def __init__(self, device, log, send_signal, host, port):
        self.host = host
        self.port = port
        self.log = log
        self.device = device
        self.send_signal = send_signal
        self.client = None

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------------------------
    # Lifecycle
    # ---------------------------
    def start(self):
        """Start the auto_reconnect thread if it is not already running."""
        if self._thread and self._thread.is_alive():
            self.log("⚠️ Hilo de LOGO ya corriendo")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.auto_reconnect, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the auto_reconnect thread and close the connection."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self.disconnect()

    def auto_reconnect(self, delay: float = 5.0):
        """Internal reconnection loop."""
        while not self._stop_event.is_set():
            if self.connect():
                self.log("✅ Conexión establecida a LOGO")
                self.device.update_connected()
                self.start_reading()
                break
            self.log(f"❌ Falló conexión LOGO. Reintento en {delay}s")
            self._stop_event.wait(delay)

    # ---------------------------
    # Connection
    # ---------------------------
    def connect(self) -> bool:
        self.log(f"▶ Conectando a LOGO {self.host}:{self.port}…")
        try:
            self.client = ModbusTcpClient(
                host=self.host, port=self.port, timeout=1.0, retries=0
            )
            if self.client.connect():
                return True
            self.log(f"❌ No se pudo conectar a {self.host}:{self.port}")
            return False
        except Exception as e:
            self.log(f"❌ Exception al conectar LOGO: {e}")
            return False

    def disconnect(self) -> None:
        if self.client:
            try:
                self.client.close()
                self.log("⚠️ LOGO desconectado")
            except Exception as e:
                self.log(f"Error al cerrar conexión LOGO: {e}")
            finally:
                self.client = None

    def is_connected(self) -> bool:
        if not self.client:
            return False
        try:
            if hasattr(self.client, "is_socket_open"):
                return self.client.is_socket_open()
            return getattr(self.client, "connected", False)
        except Exception:
            return False

    # ---------------------------
    # Commands
    # ---------------------------
    def _get_logo_config(self):
        modbus_config = getattr(self.device, "device", {}).get("modbusConfig")
        if not isinstance(modbus_config, dict):
            return None

        channels = modbus_config.get("channels")
        if isinstance(channels, dict) and isinstance(channels.get("logo"), dict):
            return channels["logo"]

        return modbus_config

    def _get_command(self, name: str):
        config = self._get_logo_config()
        if isinstance(config, dict):
            commands = config.get("commands")
            if isinstance(commands, dict) and isinstance(commands.get(name), dict):
                return commands[name]
        return LOGO_COMMANDS.get(name)

    def _write_command_value(self, command_name: str, value_name: str = "on") -> bool:
        command = self._get_command(command_name)
        if not isinstance(command, dict):
            self.log(f"⚠️ Comando LOGO no configurado: {command_name}")
            return False

        values = command.get("values")
        if not isinstance(values, dict) or value_name not in values:
            self.log(f"⚠️ Valor LOGO no configurado: {command_name}.{value_name}")
            return False

        try:
            address = int(command["address"])
            value = bool(int(values[value_name]))
        except (KeyError, TypeError, ValueError):
            self.log(f"⚠️ Comando LOGO inválido: {command_name}.{value_name}")
            return False

        return self.write_coil(address, value)

    def turn_on(self) -> bool:
        if self.is_connected():
            ok = self._write_command_value("turnOn")
            self.log("✅ LOGO encendido" if ok else "❌ Error al encender LOGO")
            return ok
        return False

    def turn_off(self) -> bool:
        if self.is_connected():
            ok = self._write_command_value("turnOff")
            self.log("✅ LOGO apagado" if ok else "❌ Error al apagar LOGO")
            return ok
        return False

    def restart(self) -> bool:
        if self.is_connected():
            ok = self._write_command_value("restart")
            self.log("✅ LOGO reiniciado" if ok else "❌ Error al reiniciar LOGO")
            return ok
        return False

    # ---------------------------
    # Reading / Writing
    # ---------------------------
    def write_coil(self, address: int, value: bool) -> bool:
        try:
            rr = self.client.write_coil(address, bool(value))
            return (rr is not None) and (not rr.isError())
        except Exception as e:
            self.log(f"❌ Error escribiendo coil {address}: {e}")
            return False

    def read_registers(self, start_address: int, count: int) -> list[int] | None:
        try:
            rr = self.client.read_holding_registers(address=start_address, count=count)
            if rr and not rr.isError():
                return rr.registers
            self.log(f"⚠️ Error leyendo registers: {rr}")
            return None
        except Exception as e:
            self.log(f"❌ Exception leyendo registers: {e}")
            return None

    # ---------------------------
    # Polling
    # ---------------------------
    def _get_signal_map(self) -> dict[str, int]:
        config = self._get_logo_config()
        if not isinstance(config, dict):
            return SIGNAL_LOGO_DIR

        config_map = config.get("registers")
        if not isinstance(config_map, dict):
            return SIGNAL_LOGO_DIR

        registers: dict[str, int] = {}
        for key, value in config_map.items():
            try:
                address = value.get("address") if isinstance(value, dict) else value
                registers[str(key)] = int(address)
            except (TypeError, ValueError):
                self.log(f"⚠️ Registro LOGO inválido para {key}: {value}")

        return registers or SIGNAL_LOGO_DIR

    def _get_status_types(self):
        config = self._get_logo_config()
        if not isinstance(config, dict):
            return LOGO_STATUS_TYPES

        types = config.get("types")
        if isinstance(types, dict):
            status_types = types.get("status")
            if isinstance(status_types, dict):
                return status_types

        return LOGO_STATUS_TYPES

    def poll_registers(self, addresses: list[int], interval: float = 0.5) -> threading.Thread:
        def _poll():
            failure_count = 0
            while not self._stop_event.is_set():
                regs_group: dict[int, int] = {}
                for addr in addresses:
                    try:
                        regs = self.read_registers(addr, 1)
                        if regs is not None:
                            regs_group[addr] = regs[0]
                            failure_count = 0
                        else:
                            failure_count += 1
                    except Exception as e:
                        self.log(f"Exception polling {addr}: {e}")
                        failure_count += 1
                if failure_count >= 3:
                    self.log("⚠️ LOGO parece desconectado")
                    self.device.update_connected()
                    self.start()  # relaunch auto_reconnect
                    return
                time.sleep(interval)
                self._read_callback(regs_group)

        thread = threading.Thread(target=_poll, daemon=True)
        thread.start()
        return thread

    def start_reading(self) -> None:
        if self.is_connected():
            signal_map = self._get_signal_map()
            addrs = list(dict.fromkeys(signal_map.values()))
            self.poll_registers(addrs)
    def update_config(self, host=None, port=None) -> bool:
        """Update LOGO! parameters and reconnect if needed."""
        changed = False

        if host and host != self.host:
            self.host = host
            changed = True

        if port and port != self.port:
            self.port = port
            changed = True

        if changed:
            self.log(f"🔄 Updating LOGO! config: {self.host}:{self.port}")
            self.auto_reconnect()
            self.start()
            return True

        return False

    # ---------------------------
    # Signals
    # ---------------------------
    def _build_signal_from_regs(self, regs: dict[int, int]) -> dict:
        signal = {}
        signal_map = self._get_signal_map()
        status_types = self._get_status_types()

        for name, addr in signal_map.items():
            value = regs.get(addr)
            if value is None:
                continue

            if name == "status":
                signal[name] = status_types.get(
                    str(value),
                    status_types.get(
                        value,
                        {"value": f"Desconocido ({value})", "kind": "operation"}
                    )
                )
                if not isinstance(signal[name], dict):
                    signal[name] = {
                        "value": signal[name],
                        "kind": "operation",
                    }
                signal[name] = signal[name] or (
                    {"value": f"Desconocido ({value})", "kind": "operation"}
                )

            else:
                # Keep the numeric value for other registers.
                signal[name] = { "value":value, "kind": "operation"}
        return signal

    def _read_callback(self, regs):
        signal = self._build_signal_from_regs(regs)
        if not signal:
            return
        payload = {k: v for k, v in signal.items() if v is not None}
        if payload:
            self.send_signal(payload, "logo")
