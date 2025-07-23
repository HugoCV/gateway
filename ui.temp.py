import tkinter as tk
import serial.tools.list_ports
from tkinter import scrolledtext, ttk, messagebox
from mqtt.mqtt_gateway import MqttGateway, MQTT_HOST, MQTT_PORT
from config import get_gateway, start_continuous_read_in_thread, write_registers, connect_logo

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MQTT Sender")
        self.geometry("1000x700")

        # Load configuration and data
        self.gateway_cfg = get_gateway()

        # Build UI first
        self._build_ui()

        # Create gateway instance after log_widget exists
        self.gateway = MqttGateway(self._log)

    def _build_ui(self):
        # — Broker & Port —
        frm = tk.Frame(self)
        frm.pack(fill="x", padx=10, pady=5)
        tk.Label(frm, text="Broker:").grid(row=0, column=0, sticky="e")
        self.broker_var = tk.StringVar(value=MQTT_HOST)
        tk.Entry(frm, textvariable=self.broker_var).grid(row=0, column=1, sticky="we")
        tk.Label(frm, text="Port:").grid(row=0, column=2, sticky="e")
        self.port_var = tk.IntVar(value=MQTT_PORT)
        tk.Entry(frm, textvariable=self.port_var, width=6).grid(row=0, column=3)
        tk.Button(frm, text="Connect", command=self._on_connect).grid(row=0, column=4, padx=5)
        frm.columnconfigure(1, weight=1)

        # — Register Gateway —
        gw_frame = tk.LabelFrame(self, text="Register Gateway", padx=10, pady=5)
        gw_frame.pack(fill="x", padx=10, pady=5)
        tk.Label(gw_frame, text="Name:").grid(row=0, column=0, sticky="e")
        self.gw_name_var = tk.StringVar(value=self.gateway_cfg.get("name", ""))
        tk.Entry(gw_frame, textvariable=self.gw_name_var).grid(row=0, column=1, sticky="we")
        tk.Label(gw_frame, text="Organization ID:").grid(row=1, column=0, sticky="e")
        self.org_var = tk.StringVar(value=self.gateway_cfg.get("organizationId", ""))
        tk.Entry(gw_frame, textvariable=self.org_var).grid(row=1, column=1, sticky="we")
        tk.Label(gw_frame, text="Location:").grid(row=2, column=0, sticky="e")
        self.loc_var = tk.StringVar(value=self.gateway_cfg.get("location", ""))
        tk.Entry(gw_frame, textvariable=self.loc_var).grid(row=2, column=1, sticky="we")
        tk.Button(
            gw_frame, text="Register Gateway", command=self._on_send_gateway
        ).grid(row=3, column=0, columnspan=2, pady=5)
        gw_frame.columnconfigure(1, weight=1)

        # — Device Selection —
        dev_frame = tk.LabelFrame(self, text="Devices", padx=10, pady=5)
        dev_frame.pack(fill="x", padx=10, pady=5)

        # Device detail
        self.name_var = tk.StringVar()
        self.serial_var = tk.StringVar()
        self.model_var = tk.StringVar()
        tk.Label(dev_frame, text="Name:").grid(row=1, column=0, sticky="e")
        tk.Entry(dev_frame, textvariable=self.name_var).grid(row=1, column=1, sticky="we")
        tk.Button(
            dev_frame,
            text="Send Device",
            command=self._on_send_device
        ).grid(row=4, column=0, columnspan=2, pady=5)

        # — Actions and RS-485 —
        btn_frame = tk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=5)

        # Button to connect via HTTP
        tk.Button(btn_frame, text="Connect HTTP", command=connect_logo).pack(side="left", padx=5)

        # — USB Port selector —
        port_frame = tk.LabelFrame(self, text="Available USB Ports", padx=10, pady=5)
        port_frame.pack(fill="x", padx=10, pady=5)

        self.usb_combo = ttk.Combobox(port_frame, state="readonly")
        self.usb_combo.pack(side="left", padx=5, pady=5)

        def refresh_ports():
            print([p.device for p in serial.tools.list_ports.comports()])
            ports = [p.device for p in serial.tools.list_ports.comports()]
            print("ports", ports)
            self.usb_combo["values"] = ports
            if ports:
                self.usb_combo.current(0)

        tk.Button(port_frame, text="Refresh Ports", command=refresh_ports).pack(side="left", padx=5)
        # load initial ports
        refresh_ports()

        # — RS-485 input fields —
        self.reg = tk.StringVar()
        tk.Label(btn_frame, text="Register:").pack(side="left", padx=(20,5))
        tk.Entry(btn_frame, textvariable=self.reg, width=6).pack(side="left", padx=5)

        self.value = tk.StringVar()
        tk.Label(btn_frame, text="Value:").pack(side="left", padx=(20,5))
        tk.Entry(btn_frame, textvariable=self.value, width=6).pack(side="left", padx=5)
        tk.Button(
            btn_frame,
            text="Write",
            command=lambda: write_registers(1, int(self.reg.get()), int(self.value.get()))
        ).pack(side="left", padx=5)
        tk.Button(
            btn_frame,
            text="Read Register Continuously",
            command=lambda: start_continuous_read_in_thread(
                1, 8, "COM3", 9600, 4, 1, 3.0, callback=lambda val: print(f'value: {val}')
            )
        ).pack(side="left", padx=5)

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
        port = self.port_var.get().strip()
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

    def _on_send_signals(self, val):
        key = self.selected_device_var.get()
        if not key:
            return self._log("⚠ Select a device first.")
        device = self.display_map[key]
        gw_id = self.gateway_cfg.get("gatewayId")
        or_id = self.gateway_cfg.get("organizationId")
        self.gateway.send_signals(or_id, gw_id, device, val)

    def _on_send_device(self):
        key = self.selected_device_var.get()
        if not key:
            return self._log("⚠ Select a device first.")
        device = self.display_map[key]
        device['name'] = self.name_var.get().strip()
        device['model'] = self.model_var.get().strip()
        gw_id = self.gateway_cfg.get("gatewayId")
        or_id = self.gateway_cfg.get("organizationId")
        self.gateway.send_device(or_id, gw_id, device)

if __name__ == "__main__":
    app = App()
    app.mainloop()
