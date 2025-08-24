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
    def __init__(self, app, log, send_signal):
        self.log = log
        self.controller = app
        self.send_signal = send_signal
        self.client = None

    def connect(self, host: str, port: int) -> bool:
        """
        Attempt to open a Modbus TCP connection to the given host and port.
        Returns True on success, False on failure or exception.
        """
        self.log(f"▶ Conectando a {host}:{port}…")
        self.host = host
        self.port = port
        try:
            self.client = ModbusTcpClient(host=host, port=port)
            ok = self.client.connect()
            if ok:
                self.log(f"✅ Connectado al Modbus TCP al host:{host} puerto:{port}")
                return True
            else:
                self.log(f"❌La conexion a {host}:{port} fallo")
                return False

        except Exception as e:
            self.log(f"❌ Exception during TCP connect to {host}:{port}: {e}")
            return False

    def disconnect(self):
        self.client.close()

    def read_holding_registers(self, address, count=1, unit=1):
        result = self.client.read_holding_registers(address=address, count=count, unit=unit)
        return result

    
    def write_single_register(self, address: int, value: int) -> bool:
        """
        Escribe un único registro Modbus (dirección y valor).
        Gestiona errores de conexión y reintento tras reconexión.
        """
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
            # Forzar cierre + reconexión
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

    def poll_registers(
        self,
        addresses: list[int],
        interval: float = 0.5,
    ) -> threading.Thread:
        """
        Inicia un hilo en background que consulta registros en loop.

        :param addresses: Lista de direcciones de registros a leer (1 registro cada una).
        :param interval: Segundos a esperar entre ciclos de polling.
        :returns: El objeto Thread ejecutando el polling.
        """
        def _poll():
            while True:
                regs_group: dict[int, int] = {}
                for addr in addresses:
                    try:
                        regs = self.read_registers(addr, 1)
                        if regs is not None:
                            regs_group[addr] = regs[0]
                    except Exception as e:
                        self.log(f"❌ Exception polling register {addr}: {e}")
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
                # Mapeo de códigos de estado/falla
                status_map = {
                    163: "Operando",
                    97: "Alta presión (conteo)",
                    32: "Falla: bajo nivel",
                    35: "Apagado por selector",
                    33: "Selector Fuera",
                    608: "Falla bajo nivel",
                    577: "Falla de voltaje",
                    4707: "Desaceleracion",
                    545: "Reposo",
                    547: "Desaceleracion",
                    609: "Paro por alta precion",
                    673: "Encendido por selector",
                    737: "Aceleracion",
                    611: "Desaceleracion",
                    1569: "Falla de confirma",
                    4705: "En Transito",
                    739: "Operacion",
                    1633: "Falla de confirma",
                    34: "Falla: bajo nivel",
                    1: "Falla de voltaje",
                    3: "Falla de voltaje",
                    41: "Falla térmica/variador",
                    675: "Operacion",
                    161: "Arranque fallido (LOGO envía señal, contactor/variador no encienden)",
                }
                signal[name] = status_map.get(value, f"Desconocido ({value})")
            else:
                # Para los tiempos, dejamos el valor numérico tal cual
                signal[name] = value

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
        print("turn on")

    def restart(self):
        if(self.is_connected()):
            return self.write_coil(5, 1)
        print("restart")
    
    def turn_off(self):
        if(self.is_connected()):
            return self.write_coil(4, 1)

    def start_reading(self) -> None:
        if(self.client):
            addrs = list(dict.fromkeys(SIGNAL_LOGO_DIR.values()))
            self.poll_registers(addrs)

    def write_coil(self, address: int, value: bool) -> bool:
        """Write coil and returns True if no error."""
        try:
            rr = self.client.write_coil(address, bool(value))
            print("logo rc", rr)
            return (rr is not None) and (not rr.isError())
        except Exception:
            return False

