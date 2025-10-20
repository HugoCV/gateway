from infrastructure.modbus.base_modbus_client import BaseModbusClient
from pymodbus.client import ModbusTcpClient

class ModbusTcp(BaseModbusClient):
    def __init__(self, device, send_signal, log, ip, port, slave_id, modbus_cfg):
        super().__init__(device, send_signal, log, slave_id, modbus_cfg, "drive")
        self.ip = ip
        self.port = port

    def connect(self):
        self.client = ModbusTcpClient(host=self.ip, port=self.port, timeout=1.0)
        if self.client.connect():
            self.log(f"Conectado a {self.ip}:{self.port}")
            return True
        self.log("No se pudo conectar TCP")
        return False

    def disconnect(self):
        if self.client:
            self.client.close()
            self.client = None
            self.log("TCP desconectado")