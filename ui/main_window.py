import tkinter as tk
from tkinter import ttk, scrolledtext
from application.app_controller import AppController
from infrastructure.mqtt.mqtt_client import MqttClient
# from infrastructure.modbus.modbus_tcp import ModbusTcp
# from infrastructure.http.http_client import HttpClient
from infrastructure.config.loader import get_gateway
from ui.gateway_tab import build_gateway_tab
from ui.device_tab import build_device_tab

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Puerta de enlace")
        self.geometry("1000x1000")

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TLabel", font=("Segoe UI", 10), foreground="#222")
        self.style.configure("TEntry", font=("Segoe UI", 10), padding=5)
        self.style.configure("TButton", font=("Segoe UI", 10), padding=6)
        self.style.configure("TCombobox", font=("Segoe UI", 10))
        self.style.map("TButton",
            background=[("active", "#d9d9d9"), ("pressed", "#c0c0c0")],
            foreground=[("disabled", "#999")]
        )

        self.gateway_cfg = get_gateway()

        self.controller = AppController(self)

        self._build_ui()
        self.log_widget = self._build_log_widget()

        self._setup_gateway()

    def _build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        tab_gateway = ttk.Frame(notebook)
        notebook.add(tab_gateway, text="Gateway")
        build_gateway_tab(self, tab_gateway)

        tab_devices = ttk.Frame(notebook)
        notebook.add(tab_devices, text="Dispositivos")
        build_device_tab(self, tab_devices)

    def _build_log_widget(self):
        widget = scrolledtext.ScrolledText(self, state="disabled", height=8)
        widget.pack(fill="x", padx=15, pady=(5, 15))
        return widget

    def _log(self, message):
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", message + "\n")
        self.log_widget.configure(state="disabled")
        self.log_widget.yview("end")

    def _setup_gateway(self):
        self.mqtt_client = MqttClient(
            self._log,
            self.controller.modbus_handler.stop,
            self.controller.modbus_handler.start,
            self.controller.modbus_handler.reset
        )
        self.controller.set_mqtt_client(self.mqtt_client)

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()
