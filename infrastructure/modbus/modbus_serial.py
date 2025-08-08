import threading
import time
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
from serial import Serial
from serial.rs485 import RS485Settings

class ModbusSerial:
    """
    Manages a Modbus RTU connection over a serial port (RS-485).
    """
    def __init__(self, app, set_registers, log=print):
        self.app = app
        self.log = log
        self.set_registers = set_registers
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
                port=self.port,
                baudrate=self.baudrate,
                timeout=timeout,
                retries=3
            )
            connected = self.client.connect()
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
                    self.client.write_register(4357,  3) 
                except Exception as e:
                    self.log(f"⚠️ RS-485 mode not supported: {e}")
                self.log(f"✅ Modbus RTU connected on {self.port}@{self.baudrate} (slave={self.slave_id})")
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
                        regs_group[addr] = regs[0]
                        # self.log(f"▶ Polled register {addr}: {regs}")
                    except Exception as e:
                        self.log(f"❌ Exception polling register {addr}: {e}")
                time.sleep(interval)
                self.set_registers(regs_group)
        thread = threading.Thread(target=_poll, daemon=True)
        thread.start()
        return thread

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
            rr = self.client.write_register(address, value)
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
    
