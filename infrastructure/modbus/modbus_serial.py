import glob
from infrastructure.modbus.base_modbus_client import BaseModbusClient
from pymodbus.client import ModbusSerialClient


class ModbusSerial(BaseModbusClient):
    def __init__(self, device, send_signal, log, port, baudrate, slave_id, modbus_cfg):
        super().__init__(device, send_signal, log, slave_id, modbus_cfg, "drive")
        self.port = port
        self.baudrate = baudrate

    def connect(self):
        ports = glob.glob(self.port)
        if not ports:
            self.log("No hay puertos disponibles")
            return False
        self.client = ModbusSerialClient(port=ports[0], baudrate=self.baudrate, timeout=1)
        if self.client.connect():
            try:
                transport = getattr(self.client, "socket", None)
                if hasattr(transport, "rs485_mode"):
                    transport.rs485_mode = RS485Settings(rts_level_for_tx=True, rts_level_for_rx=False)
            except Exception:
                pass
            self.log(f"Conectado a {self.port} @ {self.baudrate}")
            return True
        self.log("No se pudo conectar serial")
        return False

    def disconnect(self):
        if self.client:
            self.client.close()
            self.client = None
            self.log("Serial desconectado")