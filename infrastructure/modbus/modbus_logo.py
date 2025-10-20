from .base_modbus_client import BaseModbusClient
from pymodbus.client import ModbusTcpClient

MODBUS_CFG = {
  "protocol": "modbus-tcp",
  "connection": "tcp",
  "deviceModel": "LOGO",
  "registers": {
    "status": {
      "address": 0,
      "scale": 1,
      "types": {
        "1": { "value": "Falla de voltaje", "kind": "fault" },
        "3": { "value": "Falla de voltaje", "kind": "fault" },
        "9": { "value": "Falla de voltaje", "kind": "fault" },
        "32": { "value": "Falla: bajo nivel", "kind": "fault" },
        "34": { "value": "Falla: bajo nivel", "kind": "fault" },
        "41": { "value": "Falla térmica/variador", "kind": "fault" },
        "97": { "value": "Alta presión (conteo)", "kind": "operation" },
        "161": { "value": "Arranque fallido (LOGO envía señal, contactor/variador no encienden)", "kind": "fault" },
        "163": { "value": "Operando", "kind": "operation" },
        "512": { "value": "Logo reiniciando", "kind": "operation" },
        "520": { "value": "Reiniciando", "kind": "operation" },
        "521": { "value": "Falla de voltaje", "kind": "fault" },
        "544": { "value": "Falla de bajo nivel", "kind": "fault" },
        "546": { "value": "Falla de bajo nivel", "kind": "fault" },
        "545": { "value": "Reposo", "kind": "operation" },
        "547": { "value": "Desaceleración", "kind": "operation" },
        "577": { "value": "Falla de voltaje", "kind": "fault" },
        "608": { "value": "Falla bajo nivel", "kind": "fault" },
        "609": { "value": "Paro por alta presión", "kind": "operation" },
        "611": { "value": "Desaceleración", "kind": "operation" },
        "673": { "value": "Encendido por selector", "kind": "operation" },
        "675": { "value": "Operación", "kind": "operation" },
        "737": { "value": "Aceleración", "kind": "operation" },
        "739": { "value": "Operación", "kind": "operation" },
        "4705": { "value": "En tránsito", "kind": "operation" },
        "4707": { "value": "Desaceleración", "kind": "operation" },
        "1569": { "value": "Falla de confirma", "kind": "fault" },
        "1633": { "value": "Falla de confirma", "kind": "fault" }
      }
    },
    "restartTime": { "address": 1, "scale": 1 },
    "voltageResetTime": { "address": 2, "scale": 1 },
    "autoResetTime": { "address": 4, "scale": 1 },
    "workHours": { "address": 5, "scale": 1 },
    "workMinutes": { "address": 6, "scale": 1 },
    "lowLevelResetTime": { "address": 8, "scale": 1 },
    "highPressureCount": { "address": 11, "scale": 1 },
    "networkPressure": { "address": 16, "scale": 1 },
    "dischargePressure": { "address": 17, "scale": 1 }
  },
}




class LogoModbusClient(BaseModbusClient):
    def __init__(self, device, log, send_signal, host, port):

        super().__init__(device, send_signal, log, slave_id=1, modbus_cfg=MODBUS_CFG, signal_group="logo")
        self.host = host
        self.port = port

    def connect(self):
        try:
            self.client = ModbusTcpClient(host=self.host, port=self.port, timeout=1)
            if self.client.connect():
                self.log("Conectado a LOGO")
                return True
        except Exception as e:
            self.log(f"Error al conectar LOGO: {e}")
        return False

    def disconnect(self):
        if self.client:
            try:
                self.client.close()
                self.log("LOGO desconectado")
            except Exception as e:
                self.log(f"Error cerrando LOGO: {e}")
            finally:
                self.client = None

    # Methods
    def turn_on(self):  return self.write_register(3, 1)
    def turn_off(self): return self.write_register(4, 1)
    def restart(self):  return self.write_register(5, 1)
