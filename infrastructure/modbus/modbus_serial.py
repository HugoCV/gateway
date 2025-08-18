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
    "dir": 16,         # si cambia, actualiza aquí
    "speed": 785,
    "alarm": 815,
    "temp": 860,
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

        Args:
            port: Serial port name, e.g. "/dev/ttyUSB0" or "COM3".
            baudrate: Baud rate for serial communication.
            slave_id: Modbus slave address.
            timeout: Read timeout in seconds.
        """
        # Save parameters
        self.port = port
        self.baudrate = baudrate
        self.slave_id = slave_id
        try:
            # Instantiate Modbus client (RTU mode)
            self.client = ModbusSerialClient(
                port=self.port,              # p.ej. "/dev/ttyUSB0"
                baudrate=self.baudrate,      # p.ej. 9600
                parity="E",                  # típico en RTU (ajústalo a tu equipo)
                stopbits=1,
                bytesize=8,
                timeout=3.0,
                retries=3,
            )
            connected = self.client.connect()
            print("connected", connected)
            if connected:
                # Configure RS-485 settings on underlying transport
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
                self.log(f"✅ Modbus RTU connected on {self.port}@{self.baudrate} (slave={self.slave_id})")
                #self.client.write_register(4357,  3, device_id=1) 
                #rq = self.client.write_register(address, 3, device_id=self.slave_id)

            else:
                self.log(f"❌ Failed to connect Modbus RTU on {self.port}@{self.baudrate}")
            return connected
        except ModbusException as e:
            self.log(f"❌ Modbus exception on connect: {e}")
            return False
        except Exception as e:
            self.log(f"❌ Error opening RS-485 port: {e}")
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
                        regs = self.read_holding_registers(addr, 1, count=1)
                        if regs:
                            regs_group[addr] = regs[0]
                        # self.log(f"▶ Polled register {addr}: {regs}")
                    except Exception as e:
                        self.log(f"❌ Exception polling register {addr}: {e}")
                time.sleep(interval)
                print("continuous read")
                self.on_modbus_serial_read_callback(regs_group)
        thread = threading.Thread(target=_poll, daemon=True)
        thread.start()
        return thread

    def read_holding_registers(self, address: int, slave_id, count: int = 1) -> list[bool] | None:
        # self.app._log(f"Leyendo el esclavo: {self.app.slave_id_var.get()}")
        """Reads `count` coils starting at `address`."""
        print("connected", self.client.connected)
        print(address, slave_id, count)
        if not self.client:
            self.log("⚠️ Client not connected. Call connect() first.")
            return None
        with self._lock:
            try:
                rr = self.client.read_holding_registers(address, count=count, device_id=slave_id)
                print("rr", rr)
                if rr and not rr.isError():
                    regs   = list(rr.registers)
                    status = getattr(rr, 'status', None)
                    return regs
                self.log(f"❌ Error reading coils: {rr}")
            except Exception as e:
                self.log(f"❌ Exception reading coils: {e}")
        return None

    def write_register(self, address: int, value: int, slave:int) -> bool:
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
            print("before write", slave)
            rr = self.client.write_register(address, value, device_id=slave)
            print("RR", rr)
            if rr and not rr.isError():
                self.log(f"▶ Escribio en registro {address} = {value}")
                return True
            else:
                self.log(f"❌ Error writing register {address}: {rr}")
        except Exception as e:
            self.log(f"❌ Exception writing register {address}: {e}")

        return False

    def start(
        self,
        port: str,
        baudrate: int = 9600,
        slave_id: int = 1,
        timeout: float = 3.0
    ) -> bool:
        """
        Alias for connect(), allowing start with parameters.
        """
        return self.connect(port, baudrate, slave_id, timeout)

    def stop(self) -> None:
        """
        Alias for disconnect().
        """
        self.disconnect()

    def reset(self) -> bool:
        """
        Reconnects by closing and reopening the serial port using stored parameters.
        """
        self.log("🔄 Resetting Modbus RTU connection...")
        self.disconnect()
        time.sleep(0.5)
        # Reuse last parameters
        return self.connect(self.port, self.baudrate, self._slave_id)

    def custom(self, fn, *args, **kwargs):
        """
        Allows executing a custom Modbus function on the client.
        `fn` should be a callable that accepts the ModbusSerialClient as first argument.
        """
        if not self.client:
            self.log("⚠️ Client not connected. Call connect() first.")
            return None
        with self._lock:
            try:
                return fn(self.client, *args, **kwargs)
            except Exception as e:
                self.log(f"❌ Exception in custom function: {e}")
                return None
            
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

            
    def on_modbus_serial_read_callback(self, regs):
        self.log("on_modbus_serial_read_callback")
        signal = self._build_signal_from_regs(regs, SIGNAL_MODBUS_SERIAL_DIR)
        for k, label in MODBUS_LABELS.items():
            v = signal.get(k, None)
            if v is not None:
                self.window._log(f"ℹ️ {label}: {v}")
        # Publicación opcional por MQTT
        print("on_send_signal", signal, "drive")
        self.send_signal(signal, "drive")
    
