# ui/main_window.py
import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
from mqtt.mqtt_client import MqttGateway
from config.loader import get_gateway
from .gateway_tab import build_gateway_tab
from .device_tab import build_device_tab
from drivers.modbus_tcp import ModbusTcp 

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Puerta de enlace")
        self.geometry("1000x700")

        self.gateway_cfg = get_gateway()
        self.device_client = None
        self.modbus_handler = ModbusTcp(self)

        self._build_ui()
        self.gateway = MqttGateway(self._log)

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        tab_gateway = tk.Frame(notebook)
        notebook.add(tab_gateway, text="Puerta de enlace")
        build_gateway_tab(self, tab_gateway)

        tab_devices = tk.Frame(notebook)
        notebook.add(tab_devices, text="Dispositivos")
        build_device_tab(self, tab_devices)

        self.log_widget = scrolledtext.ScrolledText(self, state="disabled", height=8)
        self.log_widget.pack(fill="both", padx=10, pady=5, expand=True)

    # Los handlers MQTT y guardar dispositivo se quedan aquí
    def _log(self, msg):
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", msg + "\n")
        self.log_widget.configure(state="disabled")
        self.log_widget.yview("end")

    def _on_mqtt_connect(self):
        broker = self.broker_var.get().strip()
        port = self.port_var.get()
        if not broker:
            return messagebox.showwarning("Error", "You must enter a broker.")
        self.gateway.connect(broker, port)

    def _on_send_gateway(self):
        name = self.gw_name_var.get().strip()
        org = self.org_var.get().strip()
        loc = self.loc_var.get().strip()
        if not all([name, org, loc]):
            return messagebox.showwarning("Missing data", "Complete all gateway fields.")
        self.gateway.send_gateway(name, org, loc)

    def _on_save_device(self):
        key = self.selected_device_var.get()
        if not key:
            return self._log("⚠ Select a device first.")
        for d in self.available_devices:
            if d["name"] == key:
                d["name"] = self.device_name_var.get().strip()
                d["serialNumber"] = self.serial_var.get().strip()
                d["model"] = self.model_var.get().strip()
                d["ip_address"] = self.device_ip.get().strip()
                d["ip_port"] = self.device_port.get().strip()
                break
        self.gateway.save_device(
            self.gateway_cfg.get("organizationId"),
            self.gateway_cfg.get("gatewayId"),
            d
        )
        self._log(f"💾 Device '{d['name']}' saved successfully.")
    def _on_connect_device(self):
        device_ip = self.device_ip.get().strip()
        port = self.device_port.get()
        self.modbus_handler.connect_device(device_ip, port)

    def _on_start_device(self):
        self.modbus_handler.start()

    def _on_stop_device(self):
        self.modbus_handler.stop()
