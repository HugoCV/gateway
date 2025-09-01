# drivers/logo_modbus.py
import threading
import time
from pymodbus.client import ModbusTcpClient


LOGO_LABELS = {
    "faultRec": "Voltage fault recovery time",
    "faultRes": "Fault reset time",
    "workHours": "Working hours",
    "workMinutes": "Working minutes",
    "faultLowWater": "Tank Low Water Level Fault",
    "highPressureRes": "High-pressure reset delay",
}

SIGNAL_LOGO_DIR = {
    "status": 0,
    "restartTime": 1,
    "voltageResetTime": 2,
    "autoResetTime": 4,
    "workHours": 5,
    "workMinutes": 6,
    "lowLevelResetTime": 8,
    "highPressureCount": 11,
}

class LogoModbusClient:
    def __init__(self, device, log, send_signal, host, port):
        self.host = host
        self.port = port
        self.log = log
        self.device = device
        self.send_signal = send_signal
        self.client = None
        self._reconnecting = False

    def connect(self) -> bool:
        """
        Attempt to open a Modbus TCP connection to the given host and port.
        Returns True on success, False on failure or exception.
        """
        self.log(f"▶ Conectando a logo {self.host}:{self.port}…")
        try:
            self.client = ModbusTcpClient(host=self.host, port=self.port, timeout=1.0, retries=0)
            ok = self.client.connect()
            if ok:
                print(f"Connectado al LOGO al host:{self.host} puerto:{self.port}")
                return True
            else:
                self.log(f"La conexion a {self.host}:{self.port} fallo")
                return False

        except Exception as e:
            self.log(f"Exception during TCP connect to {self.host}:{self.port}: {e}")
            return False

    def auto_reconnect(self, delay: float = 5.0):
        if getattr(self, "_reconnecting", False):
            return

        self._reconnecting = True
        print("iniciando conexion LOGO")
        self.disconnect()
        while True:
            if self.connect():
                print("Conexión establecida a LOGO")
                self.device.update_connected()
                self.start_reading()
                self._reconnecting = False
                return 

            print(f"No se pudo conectar al LOGO, reintentando en {delay}s...")
            time.sleep(delay)

    def disconnect(self) -> None:
        """
        Closes the Modbus and serial connection.
        """
        if self.client:
            try:
                port_obj = self.client.port if hasattr(self.client, 'port') else None
                self.client.close()
                if hasattr(port_obj, 'close'):
                    port_obj.close()
                self.log("Modbus TCP disconnected")
            except Exception as e:
                self.log(f"Error during disconnect: {e}")
            finally:
                self.client = None

    def read_holding_registers(self, address, count=1, unit=1):
        result = self.client.read_holding_registers(address=address, count=count, unit=unit)
        return result

    
    def write_single_register(self, address: int, value: int) -> bool:

        try:
            rr = self.client.write_register(address, value)
            return rr is not None and not rr.isError()
        except (ConnectionResetError, OSError) as e:
            self.log(f"❌ Error de conexión al escribir: {e}")
        except Exception as e:
            self.log(f"❌ Exception writing register: {e}")

        # Intento de reconexión y reintento único
        if self.connect(self.host, self.port):
            self.log("🔄 Reconnected, retrying write...")
            try:
                rr = self.client.write_register(address, value)
                return rr is not None and not rr.isError()
            except Exception as e2:
                self.log(f"❌ Retry write failed: {e2}")
        return False

    def is_connected(self) -> bool:
        """
        Comprueba si la conexión Modbus TCP sigue activa.
        """
        if not self.client:
            return False
        try:
            if hasattr(self.client, "is_socket_open"):
                return self.client.is_socket_open()
            return getattr(self.client, "connected", False)
        except Exception:
            return False

    def read_coils(self, start_address: int, count: int) -> list[bool] | None:
        """
        Lee múltiples coils (entradas/salidas digitales) contiguos con manejo de reconexión robusto.
        Devuelve una lista de booleanos o None si falla.
        """
        try:
            # Verificar conexión antes de leer
            if not self.client or not self.client.connected:
                self.log("Cliente Modbus desconectado, intentando reconectar...")
                if not self.client.connect():
                    self.log("❌ No se pudo reconectar al servidor Modbus.")
                    return None

            rr = self.client.read_coils(address=start_address, count=count, device_id=0)

            if rr and not rr.isError():
                return rr.bits  # 👈 devuelve lista de True/False

            self.log(f"⚠️ read_coils error: {rr}")
            return None

        except OSError as e:
            self.log(f"⚡ Error de conexión: {e}")
            try:
                self.client.close()
                if self.client.connect():
                    self.log("🔄 Reconexión exitosa, reintentando lectura...")
                    rr = self.client.read_coils(address=start_address, count=count, device_id=0)
                    if rr and not rr.isError():
                        return rr.bits
            except Exception as inner_e:
                self.log(f"Reconexión fallida: {inner_e}")
            return None

        except Exception as e:
            self.log(f"❌ Excepción leyendo coils: {e}")
            return None
    
    def read_registers(self, start_address: int, count: int) -> list[int] | None:
        """
        Lee múltiples holding registers contiguos con manejo de reconexión robusto.
        """
        try:
            # Verificar conexión antes de leer
            if not self.client or not self.client.connected:
                self.log("Cliente Modbus desconectado, intentando reconectar...")
                if not self.client.connect():
                    self.log("No se pudo reconectar al servidor Modbus.")
                    return None

            rr = self.client.read_holding_registers(address=start_address, count=count)

            if rr and not rr.isError():
                return rr.registers

            self.log(f"read_holding_registers error: {rr}")
            return None

        except OSError as e:
            self.log(f"Error de conexión: {e}")
            try:
                self.client.close()
                if self.client.connect():
                    self.log("🔄 Reconexión exitosa, reintentando lectura...")
                    rr = self.client.read_holding_registers(address=start_address, count=count)
                    if rr and not rr.isError():
                        return rr.registers
            except Exception as inner_e:
                self.log(f"Reconexión fallida: {inner_e}")
            return None

        except Exception as e:
            self.log(f"Exception reading registers: {e}")
            return None
    def handle_disconnect(self):
        self.disconnect()
        self.device.update_connected()
        threading.Thread(target=self.auto_reconnect, daemon=True).start()

    def poll_registers(self, addresses: list[int], interval: float = 0.5) -> threading.Thread:
        def _poll():
            failure_count = 0
            while True:
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
                        self.log(f"Exception polling register {addr}: {e}")
                        failure_count += 1

                if failure_count >= 3:
                    self.log("LogoModbusClient parece desconectado")
                    self.handle_disconnect()
                    return

                time.sleep(interval)
                self._read_callback(regs_group)

        thread = threading.Thread(target=_poll, daemon=True)
        thread.start()
        return thread
    
    def _build_signal_from_regs(self, regs: dict[int, int]) -> dict:
        signal = {}

        for name, addr in SIGNAL_LOGO_DIR.items():
            value = regs.get(addr)
            if value is None:
                continue

            if name == "status":
                status_map = {
                    163: {"value": "Operando", "kind": "operation"},
                    97: {"value": "Alta presión (conteo)", "kind": "operation"},
                    32: {"value": "Falla: bajo nivel", "kind": "fault"},
                    35: {"value": "Apagado por selector", "kind": "operation"},
                    33: {"value": "Selector Fuera", "kind": "operation"},
                    608: {"value": "Falla bajo nivel", "kind": "fault"},
                    577: {"value": "Falla de voltaje", "kind": "fault"},
                    4707: {"value": "Desaceleracion", "kind": "operation"},
                    545: {"value": "Reposo", "kind": "operation"},
                    547: {"value": "Desaceleracion", "kind": "operation"},
                    609: {"value": "Paro por alta precion", "kind": "operation"},
                    673: {"value": "Encendido por selector", "kind": "operation"},
                    737: {"value": "Aceleracion", "kind": "operation"},
                    611: {"value": "Desaceleracion", "kind": "operation"},
                    1569: {"value": "Falla de confirma", "kind": "fault"},
                    4705: {"value": "En Transito", "kind": "operation"},
                    739: {"value": "Operacion", "kind": "operation"},
                    1633: {"value": "Falla de confirma", "kind": "fault"},
                    34: {"value": "Falla: bajo nivel", "kind": "fault"},
                    1: {"value": "Falla de voltaje", "kind": "fault"},
                    3: {"value": "Falla de voltaje", "kind": "fault"},
                    41: {"value": "Falla térmica/variador", "kind": "fault"},
                    675: {"value": "Operacion", "kind": "operation"},
                    161: {"value": "Arranque fallido (LOGO envía señal, contactor/variador no encienden)", "kind": "fault"},
                }

                signal[name] = status_map.get(
                    value,
                    {"value": f"Desconocido ({value})", "kind": "operation"}
                )

            else:
                # Para otros registros dejamos el valor numérico
                signal[name] = { "value":value, "kind": "operation"}
        return signal

    def _read_callback(self, regs):
        signal = self._build_signal_from_regs(regs)

        if not signal:
            return  

        # Filter None
        payload = {k: v for k, v in signal.items() if v is not None}
        if not payload:
            return 

        self.send_signal(payload, "logo")

    def close(self):
        """Cierra la conexión TCP al dispositivo."""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
    def turn_on(self):
        if(self.is_connected()):
            return self.write_coil(3, 1)

    def restart(self):
        if(self.is_connected()):
            return self.write_coil(5, 1)
    
    def turn_off(self):
        if(self.is_connected()):
            return self.write_coil(4, 1)

    def start_reading(self) -> None:
        if(self.is_connected()):
            addrs = list(dict.fromkeys(SIGNAL_LOGO_DIR.values()))
            self.poll_registers(addrs)

    def write_coil(self, address: int, value: bool) -> bool:
        """Write coil and returns True if no error."""
        try:
            rr = self.client.write_coil(address, bool(value))
            return (rr is not None) and (not rr.isError())
        except Exception:
            return False

