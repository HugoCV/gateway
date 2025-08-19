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
    "faultRec": 2,
    "faultRes": 4,
    "workHours": 5,
    "workMinutes": 6,
    "faultLowWater": 8,
    "highPressureRes": 11,
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
    
    def read_registers(self, start_address: int, count: int) -> list[int] | None:
        """
        Lee múltiples holding registers contiguos.
        """
        try:
            rr = self.client.read_holding_registers(address=start_address, count=count)  # <- keywords
            if rr and not rr.isError():
                return rr.registers
            self.log(f"⚠️ read_holding_registers error: {rr}")
            return None
        except (ConnectionResetError, OSError) as e:
            self.log(f"❌ Error de conexión al leer registros: {e}")
            return None
        except Exception as e:
            self.log(f"❌ Exception reading registers: {e}")
            return None
    
    def write_coil(self, address: int, value: bool) -> bool:
        """Escribe un coil y devuelve True si no hubo error."""
        try:
            rr = self.client.write_coil(address, bool(value))
            return (rr is not None) and (not rr.isError())
        except Exception:
            return False

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
                        # else: se omite si error
                    except Exception as e:
                        self.log(f"❌ Exception polling register {addr}: {e}")
                time.sleep(interval)
                # Llamada al callback del controlador si existe
                self._read_callback(regs_group)
        thread = threading.Thread(target=_poll, daemon=True)
        thread.start()
        return thread
    
    def _build_signal_from_regs(self, regs: dict[int, int]) -> dict:
        return {name: regs.get(addr) for name, addr in SIGNAL_LOGO_DIR.items()}

    def _read_callback(self, regs):
        signal = self._build_logo_signal_from_regs(regs)
        for k, label in LOGO_LABELS.items():
            v = signal.get(k, None)
            if v is not None:
                self.window._log(f"ℹ️ {label}: {v}")
        # Publicación opcional por MQTT (grupo 'logo')
        print("on_send_signal", signal, "logo")
        self.send_signal(signal, "logo")

    def is_connected(self) -> bool:
        """Comprueba si la conexión TCP está abierta."""
        try:
            sock = self.client.socket
            return sock is not None and not sock._closed
        except Exception:
            return False

    def close(self):
        """Cierra la conexión TCP al dispositivo."""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
    def turn_on(self):
        print("turn on")
    
    def turn_off(self):
        print("turn off")

    def start_reading(self) -> None:
        if(self.client):
            addrs = list(dict.fromkeys(SIGNAL_LOGO_DIR.values()))
            self.poll_registers(addrs)

