import json
from config.paths import DEVICES_FILE
from config.json_storage import load_json, save_json
from domain.models.device import Device

class DeviceManager:
    def __init__(self, log_func=None):
        self.log = log_func or (lambda msg: print(msg))
        self.devices = []

    def load_devices(self):
        """Carga dispositivos desde el archivo JSON."""
        raw_list = load_json(DEVICES_FILE, [])
        self.devices = [Device(data, log_func=self.log) for data in raw_list]
        self.log(f"📦 {len(self.devices)} dispositivos cargados.")
        return self.devices

    def save_devices(self):
        """Guarda todos los dispositivos al archivo JSON."""
        data = [dev.to_dict() for dev in self.devices]
        save_json(DEVICES_FILE, data)
        self.log("💾 Dispositivos guardados.")

    def get_device_by_serial(self, serial):
        """Devuelve el dispositivo con el número de serie dado, o None."""
        return next((d for d in self.devices if d.serial_number == serial), None)

    def add_device(self, device_data=None):
        """Agrega un nuevo dispositivo con datos opcionales."""
        device_data = device_data or {
            "name": "NuevoDispositivo",
            "serialNumber": "",
            "model": "",
            "ip_address": "",
            "ip_port": ""
        }
        device = Device(device_data, log_func=self.log)
        self.devices.append(device)
        self.log(f"🆕 Dispositivo '{device.name}' agregado.")
        return device

    def to_names(self):
        """Retorna una lista con los nombres de los dispositivos."""
        return [dev.name for dev in self.devices]
