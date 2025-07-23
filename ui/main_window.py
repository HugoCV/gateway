import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
from pymodbus.client import ModbusTcpClient
import time
import threading


from .gateway_tab import build_gateway_tab
from .device_tab import build_device_tab
from .mqtt_tab import build_mqtt_tab


from mqtt.mqtt_gateway import MqttGateway
from config import get_gateway

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MQTT Sender")
        self.geometry("1000x700")

        # Load configuration
        self.gateway_cfg = get_gateway()

        # Build the interface
        self._build_ui()

        # Create gateway instance after UI is ready
        self.gateway = MqttGateway(self._log)

    def _build_ui(self):

        self.device_client = None

        # === Notebook Tabs ===
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        # Gateway Tab
        tab_gateway = tk.Frame(notebook)
        notebook.add(tab_gateway, text="Gateway")
        build_gateway_tab(self, tab_gateway)

        # Device Tab:
        tab_devices = tk.Frame(notebook)
        notebook.add(tab_devices, text="Dispositivos")
        build_device_tab(self, tab_devices)

        # Mqtt Tab:
        tab_mqtt = tk.Frame(notebook)
        notebook.add(tab_mqtt, text="Conexión")
        build_mqtt_tab(self, tab_mqtt)

        # === Log Widget ===
        self.log_widget = scrolledtext.ScrolledText(self, state="disabled", height=8)
        self.log_widget.pack(fill="both", padx=10, pady=5, expand=True)

    # ========== Methods ==========
    def _log(self, msg: str):
        """Append a message to the log widget."""
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", msg + "\n")
        self.log_widget.configure(state="disabled")
        self.log_widget.yview("end")

    def _on_mqtt_connect(self):
        """Handle Connect button."""
        broker = self.broker_var.get().strip()
        port = self.port_var.get()
        if not broker:
            return messagebox.showwarning("Error", "You must enter a broker.")
        self.gateway.connect(broker, port)

    def _on_send_gateway(self):
        """Handle Register Gateway button."""
        name = self.gw_name_var.get().strip()
        org = self.org_var.get().strip()
        loc = self.loc_var.get().strip()
        if not all([name, org, loc]):
            return messagebox.showwarning("Missing data", "Complete all gateway fields.")
        self.gateway.send_gateway(name, org, loc)

    def _on_connect_device(self):
        """Connect to Modbus device and start reading."""
        device_ip = self.device_ip.get().strip()
        port = self.device_port.get()

        # Crear cliente
        self.device_client = ModbusTcpClient(device_ip, port=port)

        # Intentar conectar
        if not self.device_client.connect():
            messagebox.showerror("Error", f"No se pudo conectar a {device_ip}:{port}")
            self.device_client = None
            return

        print(f"✅ Conectado a {device_ip}:{port}")

        # Escribir frecuencia de referencia inicial
        self.device_client.write_register(address=1, value=500)
        self.device_client.write_register(address=2, value=200)
        self.device_client.write_register(address=3, value=300)
        print("✔ Frecuencia inicial escrita (5.00 Hz)")

        # Iniciar lectura continua en segundo plano
        start_continuous_read(self)

    def _on_start_device(self):
        if self.device_client:
            self.device_client.write_register(address=0, value=1)
            self.device_client.write_register(address=1, value=500)
            print("✔ Comando enviado: RUN")
        else:
            messagebox.showwarning("Advertencia", "Debes conectar el dispositivo primero.")
    
    def _on_stop_device(self):
        if self.device_client:
            self.device_client.write_register(address=0, value=0)
            print("✔ Comando enviado: STOP")
        else:
            messagebox.showwarning("Advertencia", "Debes conectar el dispositivo primero.")

    
def start_continuous_read(self):
    def read_loop():
        while True:
            if self.device_client:
                rr = self.device_client.read_holding_registers(address=0, count=4)
                if rr.isError():
                    print("Error reading registers")
                else:
                    state, freq_ref, freq_actual, current = rr.registers
                    print(f"[READ] Estado:{state} Frecuencia Actual: {freq_actual/100:.2f}Hz Frecuencia de referencia: {freq_ref/100:.2f}Hz Corriente: {current/100:.2f}A")
            time.sleep(1)  

    t = threading.Thread(target=read_loop, daemon=True)
    t.start()
