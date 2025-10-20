# connection_manager.py
from infrastructure.modbus.modbus_tcp import ModbusTcp
from infrastructure.modbus.modbus_serial import ModbusSerial
from infrastructure.modbus.modbus_logo import LogoModbusClient

class ConnectionManager:
    """Manages per-device protocol clients (TCP, Serial, LOGO)."""
    def __init__(self, device, log, send_signal):
        self.device = device
        self.log = log
        self.send_signal = send_signal
        self.tcp = None
        self.serial = None
        self.logo = None

    def create_connections(self, cc: dict, modbus_cfg: dict):
        """Initialize only the required connections based on defaultReader."""
        try:
            default_reader = cc.get("defaultReader")
            proto = modbus_cfg.get("protocol") or modbus_cfg.get("connection")

            if default_reader == "serial" or proto in ("modbus-rtu", "serial"):
                self.serial = ModbusSerial(
                    self.device, self.send_signal, self.log,
                    cc.get("serialPort"), cc.get("baudrate"), cc.get("slaveId"), modbus_cfg
                )
                self.log("Initialized Modbus SERIAL connection")

            elif default_reader == "tcp" or proto in ("modbus-tcp", "tcp"):
                self.tcp = ModbusTcp(
                    self.device, self.send_signal, self.log,
                    cc.get("host"), cc.get("tcpPort"), cc.get("slaveId"), modbus_cfg
                )
                self.log("Initialized Modbus TCP connection")

            else:
                self.log(f"Unknown defaultReader='{default_reader}', protocol='{proto}'")

            # LOGO connection is optional and independent
            if cc.get("logoIp") and cc.get("logoPort"):
                self.logo = LogoModbusClient(
                    self.device, self.log, self.send_signal,
                    cc["logoIp"], cc["logoPort"]
                )
                self.log("🔌 Initialized LOGO! connection")

        except Exception as e:
            self.log(f"❌ Error creating connections: {e}")


    def stop_all(self):
        for conn, name in [(self.tcp, "TCP"), (self.serial, "Serial"), (self.logo, "LOGO")]:
            try:
                if conn:
                    conn.stop()
            except Exception as e:
                self.log(f"⚠️ Error stopping {name}: {e}")
