# drivers/logo_modbus.py
from __future__ import annotations

import threading
import time
from pymodbus.client import ModbusTcpClient
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
        return None
    def _get_command(self, name: str):
        config = self._get_logo_config()
        if isinstance(config, dict):
            commands = config.get("commands")
            if isinstance(commands, dict) and isinstance(commands.get(name), dict):
                return commands[name]
        return None
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
    def execute_command(self, command_name: str, value_name: str = "on") -> bool:
        return self._write_command_value(command_name, value_name)
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
            self.log("Config LOGO no disponible")
            return {}
        config_map = config.get("registers")
        if not isinstance(config_map, dict):
            self.log("Registros LOGO no configurados")
            return {}
        registers: dict[str, int] = {}
        for key, value in config_map.items():
            try:
                address = value.get("address") if isinstance(value, dict) else value
                registers[str(key)] = int(address)
            except (TypeError, ValueError):
                self.log(f"Registro LOGO invalido para {key}: {value}")
        return registers
    def _get_register_config(self, name: str):
        config = self._get_logo_config()
        if not isinstance(config, dict):
            return None
        registers = config.get("registers")
        if isinstance(registers, dict) and isinstance(registers.get(name), dict):
            return registers[name]
        return None
    def _get_type_map(self, name: str):
        config = self._get_logo_config()
        if not isinstance(config, dict):
            return {}
        types = config.get("types")
        if isinstance(types, dict) and isinstance(types.get(name), dict):
            return types[name]
        register = self._get_register_config(name)
        if isinstance(register, dict) and isinstance(register.get("types"), dict):
            return register["types"]
        return {}
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
    def _format_signal_value(self, name: str, value: int) -> dict:
        type_map = self._get_type_map(name)
        if isinstance(type_map, dict) and type_map:
            mapped = type_map.get(str(value), type_map.get(value))
            if mapped is not None:
                if isinstance(mapped, dict):
                    return mapped
                return {"value": mapped, "kind": "operation"}
            return {"value": f"Desconocido ({value})", "kind": "operation"}
        return {"value": value, "kind": "operation"}
    def _build_signal_from_regs(self, regs: dict[int, int]) -> dict:
        signal = {}
        signal_map = self._get_signal_map()
        for name, addr in signal_map.items():
            value = regs.get(addr)
            if value is None:
                continue
            signal[name] = self._format_signal_value(name, value)
        return signal
    def _read_callback(self, regs):
        signal = self._build_signal_from_regs(regs)
        if not signal:
            return
        payload = {k: v for k, v in signal.items() if v is not None}
        if payload:
            self.send_signal(payload, "logo")
