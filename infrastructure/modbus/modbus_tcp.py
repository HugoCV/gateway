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
    "dir": 6,         # ajusta si cambia
    "speed": 786,
    "alarm": 816,
    "temp": 861,
}

STATUS_TYPES_DIR = {
    0 : "stop",
    1 : "fault",
    2 : "run"
}

DIR_TYPE_DIR = {
    1: "stop",
    4: "reverse",
    65: "auto",
    66: "fwd",
    129: "auto",
    130: "fwd",
    258: "fwd",
    257: "acc"
}

DEVICE = {
    "status": {
        "address": 987,
        "values": {
            "on": 0,
            "off": 3
        }
    },
    "mode": {
        "address": 4358,
        "values": {
            "local": 2,
            "remote": 4
        }
    }
}

class ModbusTcp:
    def __init__(self, controller, send_signal, log):
        self.send_signal = send_signal
        self.controller = controller
        self.client = None
        self.log = log
        self._lock = threading.Lock()
        self.poll_interval = 0.5

    def connect(self, ip, port, slave_id) -> bool:
        self.log(f"🔌 Iniciando conexión Modbus TCP a {ip}:{port}")
        self.slave_id = slave_id
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

        except Exception as e:
            self.log(f"❌ Error conectando a {ip}:{port}: {e}")
            try:
                if self.client:
                    self.client.close()
            except Exception:
                pass
            self.client = None
            return False

    def turn_on(self) -> bool:
        self.set_remote()
        return self.write_register(address=898, value=3)

    def turn_off(self) -> bool:
        self.set_remote()
        is_turned_off = self.write_register(address=898, value=0)
        self.set_local()
        return is_turned_off

    def is_connected(self) -> bool:
        """
        Verifica si el cliente Modbus TCP sigue conectado.
        """
        if not self.client:
            return False
        try:
            # pymodbus 3.x
            if hasattr(self.client, "is_socket_open"):
                return self.client.is_socket_open()
            # fallback en otras versiones
            return getattr(self.client, "connected", False)
        except Exception:
            return False
    
    def restart(self):
        if self.client:
            result1 = self.write_register(address=901, value=1)
            result2 = self.write_register(address=901, value=0)
            result3 = self.write_register(address=898, value=2)
            
            if not result1.isError() and not result2.isError() and not result3.isError():
                self.log("✔ Comando enviado: RESET")

    def set_local(self) -> bool:
        is_local = self.write_register(address=DEVICE["mode"]["address"], value=DEVICE["mode"]["values"]["local"])
        if(is_local):
            self.log("no se pudo poner en remoto") 
        return is_local

    def set_remote(self) -> bool:
        is_remote = self.write_register(address=DEVICE["mode"]["address"], value=DEVICE["mode"]["values"]["remote"])
        if(is_remote):
            self.log("no se pudo poner en remoto") 
        return is_remote
        
    def write_register(self, address: int, value: int) -> bool:
        """
        Writes a single holding register at `address`.

        :param address: Register address to write
        :param value:   Integer value to write (0–0xFFFF)
        :returns:       True on success, False otherwise
        """
        if not self.client:
            self.log("⚠️ Client not connected. Call connect() first.")
            return False

        try:
            rr = self.client.write_register(address, value, device_id=self.slave_id)
            if rr and not rr.isError():
                self.log(f"TCP Escribio en registro {address} = {value}")
                return True
            else:
                self.log(f"Error writing register {address}: {rr}")
        except Exception as e:
            self.log(f"Exception writing register {address}: {e}")

        return False

    def start_continuous_read(self):
        def read_loop():
            while True:
                if self.client:
                    rr = self.client.read_holding_registers(address=19, count=9)
                time.sleep(5)
        threading.Thread(target=read_loop, daemon=True).start()

    def start_reading(self)-> None:
        if not self.is_connected():
            return
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
                    except Exception as e:
                        self.log(f"❌ Exception polling register {addr}: {e}")
                time.sleep(interval)
                self._read_callback(regs_group)
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
            if(name == "stat"):
                s[name] = STATUS_TYPES_DIR[v]
            if(name == "dir"):
                s[name] = DIR_TYPE_DIR[v]
            
        return s
    
    def _read_callback(self, regs):
        # Construir señal desde registros
        signal = self._build_signal_from_regs(regs, SIGNAL_MODBUS_TCP_DIR)
        if not signal:
            return  
        # Filtrar valores None en payload
        payload = {k: v for k, v in signal.items() if v is not None}
        if not payload:
            return 
        self.send_signal(payload, "drive")
    
    def read_holding_registers(self, address: int, slave_id, count: int = 1) -> list[bool] | None:
        # self.app._log(f"Leyendo el esclavo: {self.app.slave_id_var.get()}")
        """Reads `count` registers starting at `address`."""
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
                self.log(f"❌ Error reading registers: {rr}")
            except Exception as e:
                self.log(f"❌ Exception reading registers: {e}")
        return None

