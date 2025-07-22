import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
from mqtt_gateway import MqttGateway, MQTT_HOST, MQTT_PORT
from config import get_gateway, get_devices, start_continuous_read_in_thread, write_registers, connect_logo

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MQTT Sender")
        self.geometry("600x450")

        # Cargamos configuración y datos
        self.gateway_cfg = get_gateway()
        self.devices = get_devices()

        # Construimos la UI primero
        self._build_ui()

        # Instanciamos el gateway ahora que existe log_widget
        self.gateway = MqttGateway(self._log)

    def _build_ui(self):
        # — Broker & Puerto —
        frm = tk.Frame(self)
        frm.pack(fill="x", padx=10, pady=5)
        tk.Label(frm, text="Broker:").grid(row=0, column=0, sticky="e")
        self.broker_var = tk.StringVar(value=MQTT_HOST)
        tk.Entry(frm, textvariable=self.broker_var).grid(row=0, column=1, sticky="we")
        tk.Label(frm, text="Puerto:").grid(row=0, column=2, sticky="e")
        self.port_var = tk.IntVar(value=MQTT_PORT)
        tk.Entry(frm, textvariable=self.port_var, width=6).grid(row=0, column=3)
        tk.Button(frm, text="Conectar", command=self._on_connect).grid(row=0, column=4, padx=5)
        frm.columnconfigure(1, weight=1)

        # — Registrar Gateway —
        gw_frame = tk.LabelFrame(self, text="Registrar Gateway", padx=10, pady=5)
        gw_frame.pack(fill="x", padx=10, pady=5)
        tk.Label(gw_frame, text="Nombre:").grid(row=0, column=0, sticky="e")
        self.gw_name_var = tk.StringVar(value=self.gateway_cfg.get("name", ""))
        tk.Entry(gw_frame, textvariable=self.gw_name_var).grid(row=0, column=1, sticky="we")
        tk.Label(gw_frame, text="Organization ID:").grid(row=1, column=0, sticky="e")
        self.org_var = tk.StringVar(value=self.gateway_cfg.get("organizationId", ""))
        tk.Entry(gw_frame, textvariable=self.org_var).grid(row=1, column=1, sticky="we")
        tk.Label(gw_frame, text="Location:").grid(row=2, column=0, sticky="e")
        self.loc_var = tk.StringVar(value=self.gateway_cfg.get("location", ""))
        tk.Entry(gw_frame, textvariable=self.loc_var).grid(row=2, column=1, sticky="we")
        tk.Button(
            gw_frame, text="Registrar Gateway", command=self._on_send_gateway
        ).grid(row=3, column=0, columnspan=2, pady=5)
        gw_frame.columnconfigure(1, weight=1)

        # — Selección de dispositivo —
        dev_frame = tk.LabelFrame(self, text="Dispositivos", padx=10, pady=5)
        dev_frame.pack(fill="x", padx=10, pady=5)

        # Combobox de dispositivos
        self.display_map = {f"{d['name']} ({d['serialNumber']})": d for d in self.devices}
        self.selected_device_var = tk.StringVar()
        tk.Label(dev_frame, text="Seleccionar dispositivo:").grid(row=0, column=0, sticky="e")
        combo = ttk.Combobox(
            dev_frame,
            textvariable=self.selected_device_var,
            values=list(self.display_map.keys()),
            state="readonly"
        )
        combo.grid(row=0, column=1, sticky="we")
        dev_frame.columnconfigure(1, weight=1)
        combo.bind("<<ComboboxSelected>>", self._on_device_selected)

        # Detalle de dispositivo
        self.name_var = tk.StringVar()
        self.serial_var = tk.StringVar()
        self.model_var = tk.StringVar()
        tk.Label(dev_frame, text="Nombre:").grid(row=1, column=0, sticky="e")
        tk.Entry(dev_frame, textvariable=self.name_var).grid(row=1, column=1, sticky="we")
        tk.Label(dev_frame, text="Serial:").grid(row=2, column=0, sticky="e")
        tk.Label(dev_frame, textvariable=self.serial_var).grid(row=2, column=1, sticky="we")
        tk.Label(dev_frame, text="Modelo:").grid(row=3, column=0, sticky="e")
        tk.Entry(dev_frame, textvariable=self.model_var).grid(row=3, column=1, sticky="we")
        tk.Button(
            dev_frame,
            text="Enviar Dispositivo",
            command=self._on_send_device
        ).grid(row=4, column=0, columnspan=2, pady=5)

        # — Botones de acción y RS-485 —
        btn_frame = tk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=5)

        # Botón para enviar señales
        tk.Button(btn_frame, text="conectar http", command=connect_logo) \
            .pack(side="left", padx=5)

        # Campo y botón para RS-485
        self.reg = tk.StringVar()
        tk.Label(btn_frame, text="Registro:").pack(side="left", padx=(20,5))
        tk.Entry(btn_frame, textvariable=self.reg, width=6).pack(side="left", padx=5)

        self.value = tk.StringVar()
        tk.Label(btn_frame, text="Valor:").pack(side="left", padx=(20,5))
        tk.Entry(btn_frame, textvariable=self.value, width=6).pack(side="left", padx=5)
        tk.Button(
            btn_frame,
            text="Escribir",
            command=lambda: write_registers(1, int(self.reg.get()), int(self.value.get()))
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame,
            text="Leer registro continuamente",
            command=lambda: start_continuous_read_in_thread(1, 8, "COM3", 9600, 4, 1, 3.0, callback=lambda val: print(f'valor: {val}'))
        ).pack(side="left", padx=5)
        #leer_registro(slave_id=1, reg_address=0x0001)
        # — Log —
        self.log_widget = scrolledtext.ScrolledText(self, state="disabled", height=8)
        self.log_widget.pack(fill="both", padx=10, pady=5, expand=True)

    def _log(self, msg: str):
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", msg + "\n")
        self.log_widget.configure(state="disabled")
        self.log_widget.yview("end")

    def _on_device_selected(self, event):
        key = self.selected_device_var.get()
        device = self.display_map.get(key, {})
        self.name_var.set(device.get("name", ""))
        self.serial_var.set(device.get("serialNumber", ""))
        self.model_var.set(device.get("model", ""))

    def _on_connect(self):
        broker = self.broker_var.get().strip()
        port = self.port_var.get()
        if not broker:
            return messagebox.showwarning("Error", "Debes ingresar un broker.")
        self.gateway.connect(broker, port)

    def _on_send_gateway(self):
        name = self.gw_name_var.get().strip()
        org = self.org_var.get().strip()
        loc = self.loc_var.get().strip()
        if not all([name, org, loc]):
            return messagebox.showwarning("Faltan datos", "Completa todos los campos del gateway.")
        self.gateway.send_gateway(name, org, loc)

    def _on_send_signals(self, val):
        key = self.selected_device_var.get()
        if not key:
            return self._log("⚠ Selecciona un dispositivo primero.")
        device = self.display_map[key]
        gw_id = self.gateway_cfg.get("gatewayId")
        or_id = self.gateway_cfg.get("organizationId")
        self.gateway.send_signals(or_id, gw_id, device, val)

    def _on_send_device(self):
        key = self.selected_device_var.get()
        if not key:
            return self._log("⚠ Selecciona un dispositivo primero.")
        device = self.display_map[key]
        print("send")
        device['name'] = self.name_var.get().strip()
        device['model'] = self.model_var.get().strip()
        gw_id = self.gateway_cfg.get("gatewayId")
        or_id = self.gateway_cfg.get("organizationId")
        self.gateway.send_device(or_id, gw_id, device)

if __name__ == "__main__":
    app = App()
    app.mainloop()
