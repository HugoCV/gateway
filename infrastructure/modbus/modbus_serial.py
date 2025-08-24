import threading
import time
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from serial import Serial
from serial.rs485 import RS485Settings

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

SIGNAL_MODBUS_SERIAL_DIR = {
    "freqRef": 4,
    "accTime": 6,
    "decTime": 7,
    "curr": 8,
    "freq": 9,
    "volt": 10,
    "power": 12,
    "stat": 16,
    "dir": 5,       
    "speed": 785,
    "alarm": 815,
    "temp": 860,
}

STATUS_REG = {
    "address": 987,
    "values": {
        "on": 0,
        "off": 3
    }
}

DEVICE = {
    "status": {
        "address": 897,
        "values": {
            "on": 3,
            "off": 0
        }
    },
    "mode": {
        "address": 4357,
        "values": {
            "local": 2,
            "remote": 3
        }
    }
}


STATUS_TYPES_DIR = {
    0 : "stop",
    1 : "fault",
    2 : "run"
}

DIR_TYPE_DIR = {
    4: "reverse",
    1: "stop",
    129: "auto",
    130: "fwd",
    193: "acc",
    194: "fwd"
}

class ModbusSerial:
    """
    Manages a Modbus RTU connection over a serial port (RS-485).
    """
    def __init__(self, app, send_signal, log=print):
        self.app = app
        self.log = log
        self.send_signal = send_signal
        self.client: ModbusSerialClient | None = None
        self._lock = threading.Lock()
        self.poll_interval = 0.5

    def connect(
        self,
        port: str,
        baudrate: int = 9600,
        slave_id: int = 1,
        timeout: float = 3.0
    ) -> bool:
        """
        Opens the Modbus RTU client over a serial port.
        Returns True if connection succeeded.
        """
        self.port = port
        self.baudrate = baudrate
        self.slave_id = slave_id

        try:
            # Test the following
            # if not os.path.exists(self.port):
            #     self.log(f"❌ Serial device {self.port} not found.")
            #     return False

            self.client = ModbusSerialClient(
                port=self.port,
                baudrate=self.baudrate,
                parity="N",
                stopbits=1,
                bytesize=8,
                timeout=timeout,
                retries=3,
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
                    self.log(f"⚠️ RS-485 mode not supported: {e}")

                self.log(f"✅ Connected to {self.port}@{self.baudrate} (slave={self.slave_id})")
            else:
                self.log(f"❌ Failed to connect on {self.port}@{self.baudrate}")
            return connected

        except OSError as e:
            if e.errno == errno.ENOENT:
                self.log(f"❌ Device {self.port} not found.")
            elif e.errno == errno.EACCES:
                self.log(f"❌ Permission denied for {self.port}. Try adding user to 'dialout' group.")
            else:
                self.log(f"❌ OS error on {self.port}: {e}")
            return False

        except ModbusException as e:
            self.log(f"❌ Modbus exception: {e}")
            return False

        except Exception as e:
            self.log(f"❌ Unexpected error on {self.port}: {e}")
            return False

    def disconnect(self) -> None:
        """
        Closes the Modbus and serial connection.
        """
        if self.client:
            try:
                port_obj = self.client.port if hasattr(self.client, 'port') else None
                self.client.close()
                # Close underlying serial if present
                if hasattr(port_obj, 'close'):
                    port_obj.close()
                self.log("⚠️ Modbus RTU disconnected")
            except Exception as e:
                self.log(f"❌ Error during disconnect: {e}")
            finally:
                self.client = None

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
                        regs = self.read_holding_registers(addr, count=1)
                        if regs:
                            regs_group[addr] = regs[0]
                        # self.log(f"▶ Polled register {addr}: {regs}")
                    except Exception as e:
                        self.log(f"❌ Exception polling register {addr}: {e}")
                time.sleep(interval)
                self.on_modbus_serial_read_callback(regs_group)
        thread = threading.Thread(target=_poll, daemon=True)
        thread.start()
        return thread

    def is_connected(self) -> bool:
        """
        Check if the Modbus client is currently connected.
        """
        if not self.client:
            return False
        try:
            # pymodbus 3.x tiene is_socket_open()
            if hasattr(self.client, "is_socket_open"):
                return self.client.is_socket_open()
            # fallback: algunas versiones usan 'connected'
            return getattr(self.client, "connected", False)
        except Exception:
            return False

    def read_holding_registers(self, address: int, count: int = 1) -> list[bool] | None:
        """Reads `count` read_holding_registers starting at `address`."""
        if not self.client:
            self.log("⚠️ Client not connected. Call connect() first.")
            return None
        with self._lock:
            try:
                rr = self.client.read_holding_registers(address, count=count, device_id=self.slave_id)
                if rr and not rr.isError():
                    regs   = list(rr.registers)
                    status = getattr(rr, 'status', None)
                    return regs
                self.log(f"❌ Error reading read_holding_registers: {rr}")
            except Exception as e:
                self.log(f"❌ Exception reading read_holding_registers: {e}")
        return None

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
                print(f"Serial Escribio en registro {address} = {value}")
                return True
            else:
                self.log(f"❌ Error writing register {address}: {rr}")
        except Exception as e:
            self.log(f"Serial Exception writing register {address}: {e}")

        return False

    def restart(self):
        self.write_register(900, 1)
        self.write_register(900, 0)
        self.turn_on()

    def turn_on(self) -> bool:
        self.set_remote()
        return self.write_register(DEVICE["status"]["address"], DEVICE["status"]["values"]["on"])

    def turn_off(self) -> bool:
        self.set_remote()           
        is_turned_off = self.write_register(DEVICE["status"]["address"], DEVICE["status"]["values"]["off"])
        self.set_local()
        return is_turned_off
        
    def reset(self) -> bool:
        """
        Reconnects by closing and reopening the serial port using stored parameters.
        """
        self.log("🔄 Resetting Modbus RTU connection...")
        self.disconnect()
        time.sleep(0.5)
        # Reuse last parameters
        return self.connect(self.port, self.baudrate, self._slave_id)
            
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

    def set_local(self) -> bool:
        is_local = self.write_register(address=DEVICE["mode"]["address"], value=DEVICE["mode"]["values"]["local"])
        if(is_local):
            self.log("no se pudo poner en local") 
        return is_local

    def set_remote(self) -> bool:
        is_remote = self.write_register(address=DEVICE["mode"]["address"], value=DEVICE["mode"]["values"]["remote"])
        if(is_remote):
            self.log("no se pudo poner en remoto") 
        return is_remote
    
    def start_reading(self)-> None:
        if not self.is_connected():
            return
        addrs = list(dict.fromkeys(SIGNAL_MODBUS_SERIAL_DIR.values()))
        self.serial_poll = self.poll_registers(
            addresses=addrs, interval=self.poll_interval
        )


            
    def on_modbus_serial_read_callback(self, regs):
        signal = self._build_signal_from_regs(regs, SIGNAL_MODBUS_SERIAL_DIR)

        if not signal:
            return  

        # Filter None
        payload = {k: v for k, v in signal.items() if v is not None}

        if not payload:
            return 

        self.send_signal(payload, "drive")
    
