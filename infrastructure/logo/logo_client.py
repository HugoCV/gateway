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

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ---------------------------
    # Ciclo de vida
    # ---------------------------
    def start(self):
        """Lanza el hilo de auto_reconnect si no está corriendo."""
        if self._thread and self._thread.is_alive():
            self.log("⚠️ Hilo de LOGO ya corriendo")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.auto_reconnect, daemon=True)
        self._thread.start()

    def stop(self):
        """Detiene el hilo de auto_reconnect y cierra conexión."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)
        self.disconnect()

    def auto_reconnect(self, delay: float = 5.0):
        """Loop interno de reconexión."""
        while not self._stop_event.is_set():
            if self.connect():
                self.log("✅ Conexión establecida a LOGO")
                self.device.update_connected()
                self.start_reading()
                break
            self.log(f"❌ Falló conexión LOGO. Reintento en {delay}s")
            self._stop_event.wait(delay)

    # ---------------------------
    # Conexión
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
    # Comandos
    # ---------------------------
    def turn_on(self) -> bool:
        if self.is_connected():
            ok = self.write_coil(3, 1)
            self.log("✅ LOGO encendido" if ok else "❌ Error al encender LOGO")
            return ok
        return False

    def turn_off(self) -> bool:
        if self.is_connected():
            ok = self.write_coil(4, 1)
            self.log("✅ LOGO apagado" if ok else "❌ Error al apagar LOGO")
            return ok
        return False

    def restart(self) -> bool:
        if self.is_connected():
            ok = self.write_coil(5, 1)
            self.log("✅ LOGO reiniciado" if ok else "❌ Error al reiniciar LOGO")
            return ok
        return False

    # ---------------------------
    # Lectura / Escritura
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
                    self.start()  # relanza auto_reconnect
                    return
                time.sleep(interval)
                self._read_callback(regs_group)

        thread = threading.Thread(target=_poll, daemon=True)
        thread.start()
        return thread

    def start_reading(self) -> None:
        if self.is_connected():
            addrs = list(dict.fromkeys(SIGNAL_LOGO_DIR.values()))
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
            self.stop_reconnect()
            self.start()
            return True

        return False

    # ---------------------------
    # Señales
    # ---------------------------
    def _build_signal_from_regs(self, regs: dict[int, int]) -> dict:
        signal = {}

        for name, addr in SIGNAL_LOGO_DIR.items():
            value = regs.get(addr)
            if value is None:
                continue

            if name == "status":
                status_map = {
                    9: {"value": "Falla de voltaje", "kind":"fault"},
                    8: {"value": "Reiniciando", "kind":"operation"},
                    0: {"value":"Panel desenergizado", "kind": "operation"},
                    512: {"value":"Logo reiniciando", "kind": "operation"},
                    163: {"value": "Operando", "kind": "operation"},
                    97: {"value": "Alta presión (conteo)", "kind": "operation"},
                    32: {"value": "Falla: bajo nivel", "kind": "fault"},
                    35: {"value": "Apagado por selector", "kind": "operation"},
                    33: {"value": "Selector Fuera", "kind": "operation"},
                    521:  {"value": "Falla de voltaje", "kind": "fault"},
                    520:  {"value": "Reiniciando", "kind": "operation"},
                    608: {"value": "Falla bajo nivel", "kind": "fault"},
                    577: {"value": "Falla de voltaje", "kind": "fault"},
                    513: {"value": "Falla de voltaje", "kind": "fault"},
                    544: {"value": "Falla de bajo nivel", "kind": "fault"},
                    546: {"value": "Falla de bajo nivel", "kind": "fault"},
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
        payload = {k: v for k, v in signal.items() if v is not None}
        if payload:
            print(payload)
            self.send_signal(payload, "logo")
