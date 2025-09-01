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
    257: "acc",
    193: "auto"
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
    def __init__(self, device, send_signal, log, ip, port, slave_id):
        self.ip = ip
        self.port = port
        self.slave_id = slave_id
        self.send_signal = send_signal
        self.device = device
        self.client = None
        self.log = log
        self._lock = threading.Lock()
        self.poll_interval = 0.5

    def handle_disconnect(self):
        self.disconnect()
        self.device.update_connected()
        threading.Thread(target=self.auto_reconnect, daemon=True).start()

    def auto_reconnect(self, delay: float = 5.0):
        if getattr(self, "_reconnecting", False):
            return
        self._reconnecting = True
        self.disconnect()
        print("iniciando conexion")
        while True:
            if self.connect():
                print("Conexión establecida a ModbusTcp")
                self.device.update_connected()
                self.start_reading()
                self._reconnecting = False
                return  # salimos: ya está conectado y polling en marcha

            print(f"❌ No se pudo conectar TCP, reintentando en {delay}s...")
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

    def connect(self) -> bool:
        self.log(f"Iniciando conexión Modbus TCP a {self.ip}:{self.port}")
        try:
            if getattr(self, "client", None):
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None
            
            self.client = ModbusTcpClient(host=self.ip, port=self.port, timeout=1.0, retries=0)
            if not self.client.connect():
                self.log(f"No se pudo conectar a {self.ip}:{self.port}")
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None
                return False
            self.log("se connecto por medio de TCP")
            return True

        except Exception as e:
            self.log(f"Error conectando a {ip}:{port}: {e}")
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
        def _poll():
            failure_count = 0
            while True:
                regs_group = {}

                for addr in addresses:
                    try:
                        regs = self.read_holding_registers(addr, self.slave_id, count=1)
                        if regs is not None:
                            regs_group[addr] = regs[0]
                            failure_count = 0
                        if not regs:
                            failure_count += 1
                        if failure_count >= 3:
                            self.log("Modbus TCP parece desconectado")
                            self.handle_disconnect()
                            return

                    except Exception as e:
                        self.log(f"❌ Exception polling register {addr}: {e}")
                        failure_count += 1
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
                s[name] = { "value":  v * MODBUS_SCALES[name], "kind": "operation"} 
            else:
                s[name] =  { "value":  v, "kind": "operation"} 
            if(name == "stat"):
                s[name] = { "value": STATUS_TYPES_DIR.get(v, "Desconocido {v}"), "kind": "operation"} 
            if(name == "dir"):
                s[name] = { "value": DIR_TYPE_DIR.get(v, "Desconocido {v}"), "kind": "operation"}
            
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

