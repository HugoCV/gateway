from tkinter import messagebox
from infrastructure.config.loader import get_devices, get_gateway
from infrastructure.http.http_client import HttpClient
from infrastructure.modbus.modbus_tcp import ModbusTcp

class AppController:
    def __init__(self, app):
        self.app = app
        self.gateway_cfg = get_gateway()
        self.modbus_handler = ModbusTcp(self)
        self.available_devices = []

    # MQTT
    def on_mqtt_connect(self):
        broker = self.app.broker_var.get().strip()
        port = self.app.port_var.get()
        if not broker:
            return messagebox.showwarning("Error", "Debes ingresar un broker.")
        self.mqtt_client.connect(broker, port)

    def on_send_gateway(self):
        name = self.app.gw_name_var.get().strip()
        org = self.app.org_var.get().strip()
        loc = self.app.loc_var.get().strip()
        if not all([name, org, loc]):
            return messagebox.showwarning("Faltan datos", "Completa todos los campos del gateway.")
        self.mqtt_client.send_gateway(name, org, loc)

    # Devices
    def load_devices(self):
        self.available_devices = get_devices()

    def get_device_by_name(self, name):
        return next((d for d in self.available_devices if d["name"] == name), None)

    def update_device_fields(self, device):
        self.app.device_name_var.set(device["name"])
        self.app.serial_var.set(device["serialNumber"])
        self.app.model_var.set(device["model"])
        self.app.device_ip.set(device["ip_address"])
        self.app.device_port.set(device["ip_port"])

    def refresh_device_list(self):
        device_names = [d["name"] for d in self.available_devices]
        self.app.device_combo["values"] = device_names
        if device_names:
            self.app.device_combo.current(0)
            self.update_device_fields(self.available_devices[0])

    def on_save_device(self):
        key = self.app.selected_device_var.get()
        if not key:
            return self.app._log("⚠ Selecciona un dispositivo.")
        device = self.get_device_by_name(key)
        if not device:
            return self.app._log("⚠ Dispositivo no encontrado.")

        device["name"] = self.app.device_name_var.get().strip()
        device["serialNumber"] = self.app.serial_var.get().strip()
        device["model"] = self.app.model_var.get().strip()
        device["ip_address"] = self.app.device_ip.get().strip()
        device["ip_port"] = self.app.device_port.get().strip()

        self.mqtt_client.save_device(
            self.gateway_cfg.get("organizationId"),
            self.gateway_cfg.get("gatewayId"),
            device
        )
        self.refresh_device_list()
        self.app._log(f"Dispositivo '{device['name']}' guardado correctamente.")

    def set_mqtt_client(self, mqtt_client):
        self.mqtt_client = mqtt_client

    def on_add_device(self):
        new_device = {
            "name": "NuevoDispositivo",
            "serialNumber": "",
            "model": "",
            "ip_address": "",
            "ip_port": ""
        }
        self.available_devices.append(new_device)
        self.refresh_device_list()
        self.app.device_combo.current(len(self.available_devices) - 1)
        self.update_device_fields(new_device)
        self.app._log("Nuevo dispositivo creado.")

    def on_connect_device(self):
        ip = self.app.device_ip.get().strip()
        port = self.app.device_port.get()
        if not ip or not port:
            return self.app._log("⚠️ IP o puerto no definidos.")

        self.modbus_handler.connect_device(ip, port)

        if hasattr(self.app, "http_client"):
            self.app.http_client.start_continuous_read()
            self.app._log("🔁 Lectura HTTP iniciada.")
        else:
            self.app._log("⚠️ HTTPClient no está configurado. Selecciona un dispositivo primero.")

    def on_start_device(self):
        self.modbus_handler.start()

    def on_stop_device(self):
        self.modbus_handler.stop()

    def on_reset_device(self):
        self.modbus_handler.reset()

    def on_set_remote(self):
        self.modbus_handler.set_remote()

    def on_set_local(self):
        self.modbus_handler.set_local()

    def on_select_device(self, event=None):
        selected_name = self.app.selected_device_var.get()
        device = self.get_device_by_name(selected_name)
        if not device:
            self.app._log("Dispositivo no encontrado.")
            return

        self.update_device_fields(device)

        ip = device.get("ip_address", "").strip()
        port = device.get("http_port", "").strip() or device.get("ip_port", "").strip()

        if ip and port:
            base_url = f"http://{ip}:{port}/api/dashboard"
            self.app.http_client = HttpClient(self.app, base_url=base_url)
            self.app._log(f"🌐 HTTPClient configurado con: {base_url}")
        else:
            self.app._log("⚠️ IP o puerto HTTP no definidos.")

    # === HTTP Client ===
    def on_connect_http(self):
        self.app._log("🌐 HTTP Client: Connect button pressed")

    # === Modbus Serial ===
    def on_connect_modbus_serial(self):
        self.app._log("🔌 Modbus Serial: Connect button pressed")

    def on_start_modbus_serial(self):
        self.app._log("▶️ Modbus Serial: Start button pressed")

    def on_stop_modbus_serial(self):
        self.app._log("⏹ Modbus Serial: Stop button pressed")

    def on_reset_modbus_serial(self):
        self.app._log("🔁 Modbus Serial: Reset button pressed")

    def on_custom_modbus_serial(self):
        self.app._log("⚙️ Modbus Serial: Custom button pressed")

    # === Modbus TCP ===
    def on_connect_modbus_tcp(self):
        self.app._log("🌐 Modbus TCP: Connect button pressed")

    def on_start_modbus_tcp(self):
        self.app._log("▶️ Modbus TCP: Start button pressed")

    def on_stop_modbus_tcp(self):
        self.app._log("⏹ Modbus TCP: Stop button pressed")

    def on_reset_modbus_tcp(self):
        self.app._log("🔁 Modbus TCP: Reset button pressed")

    def on_custom_modbus_tcp(self):
        self.app._log("⚙️ Modbus TCP: Custom button pressed")
