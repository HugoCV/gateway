from domain.models.device import Device
import json
from infrastructure.activity_log import connection_summary, log_value, modbus_summary

class DeviceManager:
    def __init__(self, mqtt_client, refresh_devices, log_func=None):
        # Initialize the DeviceManager with an optional logging function
        self.log = log_func or (lambda msg: print(msg))
        self.devices = []
        self.mqtt_client = mqtt_client
        self.refresh_devices = refresh_devices

    def load_devices(self):
        def _cb(c,u,m):
            try:
                data = json.loads(m.payload.decode("utf-8"))
                self.set_devices(data["devices"])
            except Exception as error:
                self.log(f"❌ No se pudo procesar la configuración de dispositivos: {type(error).__name__}.")

        try:
            self.mqtt_client.request_devices(
                _cb
            )
        except Exception as e:
            self.log(f"⚠️ MQTT fetch failed: {e}")
            return None
    def set_devices(self, devices: list):
        if not isinstance(devices, list) or any(not isinstance(d, dict) for d in devices):
            raise ValueError('Se esperaba una lista de dispositivos.')
        self.log(f"Configuración recibida por MQTT: {len(devices)} dispositivo(s).")
        for device in devices:
            self.log(
                f"Dispositivo {log_value(device.get('serialNumber'))}, "
                f"nombre={log_value(device.get('name'))}; "
                f"conexión: {connection_summary(device.get('connectionConfig'))}; "
                f"Modbus: {modbus_summary(device.get('modbusConfig'))}"
            )
        self.devices = devices
        self.refresh_devices(devices)
        self.log(f"Configuración cargada: {len(devices)} dispositivo(s). Conexiones iniciadas.")

    def read_http_fault(self):
        fault_history = self.http_handler.read_fault_history_sync()
        if fault_history:
            self.window._log(f"Historial recibido: {fault_history}")
        else:
            self.window._log("No se pudo obtener el historial.")

    def get_device_by_serial(self, serial):
        """
        Return the device with the given serial number, or None if not found.
        """
        return next((d for d in self.devices if d.serial_number == serial), None)

    def add_device(self, device_data=None):
        """
        Add a new device with optional initial data.
        """
        default_data = {
            "name": "NewDevice",
            "serialNumber": "",
            "model": "",
            "type": "",
            "ip_address": "",
            "ip_port": "",
            "tcp_ip": "",
            "tcp_port": "",
            "serial_port": "",
            "baudrate": None,
            "slave_id": None,
            "signals": []
        }
        init_data = device_data or default_data
        device = Device(**init_data)
        self.devices.append(device)
        self.log(f"🆕 Device '{device.name}' added.")
        return device

    def to_names(self):
        """
        Return a list of the names of all devices.
        """
        return [dev.name for dev in self.devices]
