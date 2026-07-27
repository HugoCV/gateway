import threading
import time
import os
import glob
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from serial.rs485 import RS485Settings
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
        # Thread control
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._reconnecting = False
    def _get_signal_map(self) -> dict[str, int]:
        config = self._get_modbus_config()
        if not isinstance(config, dict):
            self.log("Config Modbus Serial no disponible")
            return {}
        config_map = config.get("registers")
        if not isinstance(config_map, dict):
            self.log("Registros serial no configurados")
            return {}
        registers: dict[str, int] = {}
        for key, value in config_map.items():
            try:
                address = value.get("address") if isinstance(value, dict) else value
                registers[str(key)] = int(address)
            except (TypeError, ValueError):
                self.log(f"Registro serial invalido para {key}: {value}")
        return registers
    def _get_modbus_config(self):
        modbus_config = getattr(self.device, "device", {}).get("modbusConfig")
        if not isinstance(modbus_config, dict):
            return None
        channels = modbus_config.get("channels")
        if isinstance(channels, dict):
            direct_config = channels.get("direct")
            if (
                isinstance(direct_config, dict)
                and direct_config.get("protocol") == "modbus-rtu"
            ):
                return direct_config
        return None
    def _get_command(self, name: str):
        config = self._get_modbus_config()
        if isinstance(config, dict):
            commands = config.get("commands")
            if isinstance(commands, dict) and isinstance(commands.get(name), dict):
                return commands[name]
        return None
    def _write_command_value(self, command_name: str, value_name: str) -> bool:
        command = self._get_command(command_name)
        if not isinstance(command, dict):
            self.log(f"⚠️ Comando serial no configurado: {command_name}")
            return False
        values = command.get("values")
        if not isinstance(values, dict) or value_name not in values:
            self.log(f"⚠️ Valor serial no configurado: {command_name}.{value_name}")
            return False
        try:
            address = int(command["address"])
            value = int(values[value_name])
        except (KeyError, TypeError, ValueError):
            self.log(f"⚠️ Comando serial inválido: {command_name}.{value_name}")
            return False
        if command_name == "status" and value_name in ("on", "off"):
            action = "encender" if value_name == "on" else "apagar"
            self.log(
                f"🔌 Modbus Serial: enviando comando para {action} "
                f"(address={address}, value={value}, slaveId={self.slave_id})"
            )
        return self.write_register(address, value)
    def execute_command(self, command_name: str, value_name: str = "on") -> bool:
        return self._write_command_value(command_name, value_name)
    # ---------------------------
    # Lifecycle
    # ---------------------------
    def start(self):
        """Start the auto_reconnect thread if it is not already running."""
        if self._thread and self._thread.is_alive():
            self.log("⚠️ ModbusSerial: ya hay un hilo corriendo")
            return
        self.log("▶️ START Modbus Serial")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.auto_reconnect, daemon=True)
        self._thread.start()
    def stop(self):
        """Stop the reconnect loop and close the connection."""
        self.log("⏹️ STOP Modbus Serial")
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            if threading.current_thread() != self._thread:  # avoid self-join
                self._thread.join(timeout=1)
        self.disconnect()
    def auto_reconnect(self, delay=5.0):
        """Automatic reconnection loop."""
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
    # Connection
    # ---------------------------
    def connect(self, timeout: float = 1.0) -> bool:
        """Open the Modbus RTU connection over a serial port."""
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
        """Close the Modbus/serial connection."""
        if self.client:
            try:
                self.client.close()
                self.log("⚠️ Modbus RTU disconnected")
            except Exception as e:
                self.log(f"❌ Error al desconectar: {e}")
            finally:
                self.client = None
    # ---------------------------
    # Register polling
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
                    self.start()  # relaunch auto_reconnect
                    return
                self._stop_event.wait(interval)
                self.on_modbus_serial_read_callback(regs_group)
        thread = threading.Thread(target=_poll, daemon=True)
        thread.start()
        return thread
    # ---------------------------
    # Utilities
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
        ok = self._write_command_value("restart", "on")
        self._write_command_value("restart", "off")
        self.turn_on()
        return ok
    def turn_on(self) -> bool:
        return self._write_command_value("status", "on")
    def turn_off(self) -> bool:
        return self._write_command_value("status", "off")
    def _format_signal_value(self, _name: str, value: int) -> dict:
        return {"value": value, "kind": "operation"}
    def _build_signal_from_regs(self, regs: dict[int, int], modbus_dir) -> dict:
        s = {}
        for name, addr in modbus_dir.items():
            v = regs.get(addr)
            if v is None:
                s[name] = None
                continue
            s[name] = self._format_signal_value(name, v)
        return s
    def set_local(self) -> bool:
        ok = self._write_command_value("mode", "local")
        self.log("✅ Puesto en local" if ok else "❌ No se pudo poner en local")
        return ok
    def set_remote(self) -> bool:
        ok = self._write_command_value("mode", "remote")
        self.log("✅ Puesto en remoto" if ok else "❌ No se pudo poner en remoto")
        return ok
    def start_reading(self):
        if not self.is_connected():
            return
        signal_map = self._get_signal_map()
        addrs = list(dict.fromkeys(signal_map.values()))
        self.serial_poll = self.poll_registers(addresses=addrs, interval=self.poll_interval)
    def on_modbus_serial_read_callback(self, regs):
        signal = self._build_signal_from_regs(regs, self._get_signal_map())
        payload = {k: v for k, v in signal.items() if v is not None}
        if payload:
            self.send_signal(payload, "direct")
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
            self.log(f"🔄 Updating serial config: {self.baudrate}:{self.port}, slave={self.slave_id}")
            self.stop()
            self.start()
            return True
        return False
