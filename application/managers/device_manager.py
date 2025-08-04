import json
from config.paths import DEVICES_FILE
from config.json_storage import load_json, save_json
from domain.models.device import Device

class DeviceManager:
    def __init__(self, log_func=None):
        # Initialize the DeviceManager with an optional logging function
        self.log = log_func or (lambda msg: print(msg))
        self.devices = []

    def load_devices(self):
        """
        Load devices from the JSON file.
        """
        raw_list = load_json(DEVICES_FILE, [])
        # Instantiate Device objects from raw data
        self.devices = [Device(**data) for data in raw_list]
        self.log(f"📦 Loaded {len(self.devices)} devices.")
        return self.devices

    def save_devices(self):
        """
        Save all devices to the JSON file.
        """
        data = [dev.to_dict() for dev in self.devices]
        save_json(DEVICES_FILE, data)
        self.log("💾 Devices saved.")

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
