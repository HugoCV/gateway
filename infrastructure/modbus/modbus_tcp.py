import time
import threading
from pymodbus.client import ModbusTcpClient

MODBUS_LABELS = {
    "freqRef": "Referencia de frecuencia",
    "accTime": "Tiempo de aceleración",
    "decTime": "Tiempo de desaceleración",
    "curr":    "Amperaje de salida",
    "freq":    "Frecuencia de salida",
    "volt":    "Voltaje de salida",
    "voltDcLink": "Voltaje DC Link",
    "power":   "Potencia en kW",
    "stat":    "Estado",
    "dir":     "Dirección",
    "speed":   "Velocidad (rpm)",
    "alarm":   "Alarma",
    "temp":    "Temperatura",
    "fault":   "Falla",
}

MODBUS_SCALES = {
    "curr": 0.1,      # /10
    "power": 0.1,     # /10
    "freqRef": 0.01,  # /100
    "freq": 0.01,     # /100
}

SIGNAL_MODBUS_TCP_DIR = {
    "freqRef": 5,
    "accTime": 7,
    "decTime": 8,
    "curr": 9,
    "freq": 10,
    "volt": 11,
    "voltDcLink": 12,
    "power": 13,       # si no se puede saber, devuelves None si no existe
    "fault": 15,
    "stat": 17,        # 0=stop 1=falla 2=operacion
    "dir": 19,         # ajusta si cambia
    "speed": 786,
    "alarm": 816,
    "temp": 861,
}

class ModbusTcp:
    def __init__(self, controller, send_signal, log):
        self.send_signal = send_signal
        self.controller = controller
        self.client = None
        self.log = log
        self._lock = threading.Lock()

    def connect(self, ip, port) -> bool:
        self.log(f"🔌 Iniciando conexión {ip}:{port}")
        try:
            port = int(port)

            # Cierra cliente previo si existía
            if getattr(self, "client", None):
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None

            self.client = ModbusTcpClient(host=ip, port=port, timeout=3.0)

            if not self.client.connect():
                self.log(f"❌ No se pudo conectar a {ip}:{port}")
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None
                return False

            self.log(f"✅ Conectado a {ip}:{port}")

        except Exception as e:
            self.log(f"❌ Error conectando a {ip}:{port}: {e}")
            try:
                if self.client:
                    self.client.close()
            except Exception:
                pass
            self.client = None
            return False

    def turn_on(self):
        if self.client:
            result = self.client.write_register(address=898, value=3)
            self.log(f"resultado {result}")
            if not result.isError():
                self.log("✔ Comando enviado: RUN")

    def turn_off(self):
        if self.client:
            result = self.client.write_register(address=898, value=0)
            self.log(f"resultado {result}")
            if not result.isError():
                self.log("✔ Comando enviado: STOP")
    
    def restart(self):
        if self.client:
            result1 = self.client.write_register(address=901, value=1)
            result2 = self.client.write_register(address=901, value=0)
            result3 = self.client.write_register(address=898, value=2)
            
            if not result1.isError() and not result2.isError() and not result3.isError():
                self.log("✔ Comando enviado: RESET")

    def set_local(self):
        rr = self.client.write_register(address=4358, value=4)
        if rr is None or rr.isError():
            self.log("⚠️ Conectado, pero falló write_register(4358, 2)")
        else:
            self.log("📝 write_register(4358, 2) OK")

        return True

    def set_remote(self):
        self.remoto = self.client.write_register(address=4358, value=4)
        
    def write_register(self, address: int, value: int):
        self.client.write_register(address=address, value=value)

    def start_continuous_read(self):
        def read_loop():
            while True:
                if self.client:
                    rr = self.client.read_holding_registers(address=19, count=9)
                    print(rr)
                time.sleep(5)
        threading.Thread(target=read_loop, daemon=True).start()

    def start_reading(self)-> None:
        self.set_local()
        addrs = list(dict.fromkeys(SIGNAL_MODBUS_TCP_DIR.values()))
        self.tcp_poll = self.poll_registers(
            addresses=addrs, interval=self.poll_interval
        )

    def poll_registers(
        self,
        addresses: list[int],
        interval: float = 0.5
    ) -> threading.Thread:
        """
        Starts a background thread that continuously polls holding registers.

        :param addresses: List of register addresses to read (count=1 each).
        :param interval: Seconds to wait between polling cycles.
        :returns: The Thread object running the polling loop.
        """
        def _poll():
            while True:
                regs_group = {}
                for addr in addresses:
                    try:
                        regs = self.read_holding_registers(addr, 1, count=1)
                        regs_group[addr] = regs[0]
                        # self.log(f"▶ Polled register {addr}: {regs}")
                    except Exception as e:
                        self.log(f"❌ Exception polling register {addr}: {e}")
                time.sleep(interval)
                self._read_callback(regs_group)
                # self.set_registers(regs_group)
        thread = threading.Thread(target=_poll, daemon=True)
        thread.start()
        return thread
    
    def _build_signal_from_regs(self, regs: dict[int, int], modbus_dir) -> dict:
        """
        Crea dict de señal a partir de registros, aplicando escalas definidas en MODBUS_SCALES.
        """
        s = {}
        for name, addr in modbus_dir.items():
            v = regs.get(addr)
            if v is None:
                s[name] = None
                continue
            if name in MODBUS_SCALES:
                s[name] = v * MODBUS_SCALES[name]
            else:
                s[name] = v
        return s
    
    def _read_callback(self, regs):
        signal = self._build_signal_from_regs(regs, SIGNAL_MODBUS_TCP_DIR)
        for k, label in MODBUS_LABELS.items():
            v = signal.get(k, None)
            if v is not None:
                self.window._log(f"ℹ️ {label}: {v}")
        print("on_send_signal", signal, "drive")
        self.send_signal(signal, "drive")
        # self.on_send_signal(signal, "drive")
    
    def read_holding_registers(self, address: int, slave_id, count: int = 1) -> list[bool] | None:
        # self.app._log(f"Leyendo el esclavo: {self.app.slave_id_var.get()}")
        """Reads `count` coils starting at `address`."""
        if not self.client:
            self.log("⚠️ Client not connected. Call connect() first.")
            return None
        with self._lock:
            try:
                rr = self.client.read_holding_registers(address, count=count)
                if rr and not rr.isError():
                    regs   = list(rr.registers)
                    status = getattr(rr, 'status', None)
                    # self.log(f"▶Registro={address}, Respuesta={regs}, Estado={status}")
                    return regs
                self.log(f"❌ Error reading coils: {rr}")
            except Exception as e:
                self.log(f"❌ Exception reading coils: {e}")
        return None
