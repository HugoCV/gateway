import tkinter as tk
import queue
import re
import time
from datetime import datetime
from tkinter import ttk, scrolledtext, messagebox
from ui.service_client import ServiceClient
from ui.service_status import service_presentation

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Puerta de enlace")
        self.geometry("1200x1000")

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TLabel", font=("Segoe UI", 10), foreground="#222")
        self.style.configure("TEntry", font=("Segoe UI", 10), padding=5)
        self.style.configure("TButton", font=("Segoe UI", 10), padding=6)
        self.style.configure(
            "Section.TButton",
            font=("Segoe UI", 11, "bold"),
            padding=(12, 10),
            anchor="w",
        )
        self.style.configure("TCombobox", font=("Segoe UI", 10))
        self.style.map("TButton",
            background=[("active", "#d9d9d9"), ("pressed", "#c0c0c0")],
            foreground=[("disabled", "#999")]
        )
        self.style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

        # Treeview color tags
        self.style.configure("Treeview",
            background="#ffffff",
            fieldbackground="#ffffff",
            rowheight=25
        )
        self.style.map("Treeview", background=[('selected', '#0078D7')])

        self.device_tree_tags_configured = False
        self._collapsible_sections = []
        self._key_event_ids = []
        self._last_key_events = {}
        self._ui_queue = queue.Queue()
        self._gateway_identity = None
        self._service_available = False
        self._save_pending = False
        self._system_service = {}
        self.system_service_var = tk.StringVar()
        self.system_service_label = ttk.Label(self, textvariable=self.system_service_var)
        self.system_service_label.pack(anchor="w", padx=15, pady=(10, 0))
        self.startup_status_var = tk.StringVar()
        self.startup_status_label = ttk.Label(self, textvariable=self.startup_status_var)
        self.startup_status_label.pack(anchor="w", padx=15)
        self.service_status_var = tk.StringVar()
        self.service_status_label = ttk.Label(self, textvariable=self.service_status_var)
        self.service_status_label.pack(anchor="w", padx=15)
        self.service_hint_var = tk.StringVar()
        ttk.Label(self, textvariable=self.service_hint_var, wraplength=900).pack(anchor="w", padx=15)
        self._refresh_service_status()


        self._build_gateway_config_widget()
        self._build_connectivity_widget()
        self._build_key_events_widget()
        self._build_device_list_widget()
        self.log_widget = self._build_log_widget()
        self.after(100, self._drain_ui_queue)
        self.controller = ServiceClient(self._ui_queue)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self):
        """Disconnect this window without stopping the service or its devices."""
        if hasattr(self, "controller"):
            self.controller.close()
        self.destroy()

    def _create_collapsible_section(self, title, pady=5):
        """Create a section whose contents are hidden until its header is clicked."""
        container = ttk.Frame(self)
        container.pack(fill="x", padx=15, pady=pady)

        body = ttk.Frame(container, padding=15, relief="groove", borderwidth=1)
        expanded = tk.BooleanVar(value=False)
        title_var = tk.StringVar(value=f"▶  {title}")

        def toggle():
            if expanded.get():
                body.pack_forget()
                expanded.set(False)
                title_var.set(f"▶  {title}")
            else:
                body.pack(fill="x", pady=(2, 0))
                expanded.set(True)
                title_var.set(f"▼  {title}")

        header = ttk.Button(
            container,
            textvariable=title_var,
            command=toggle,
            style="Section.TButton",
        )
        header.pack(fill="x")
        self._collapsible_sections.append((container, header, body, expanded))
        return body

    def _build_gateway_config_widget(self):
        """Create the gateway configuration widget."""
        frame = self._create_collapsible_section(
            "Configuración de Gateway",
            pady=(15, 5),
        )

        frame.columnconfigure(1, weight=1)

        # Organization ID
        ttk.Label(frame, text="Organization ID:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.org_id_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.org_id_var).grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        # Gateway ID
        ttk.Label(frame, text="Gateway ID:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.gw_id_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.gw_id_var).grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        # Save Button
        self.save_button = ttk.Button(frame, text="Guardar y reiniciar servicio",
                                      command=self._save_gateway_config, state="disabled")
        self.save_button.grid(row=2, column=1, sticky="e", padx=5, pady=10)

    def _build_connectivity_widget(self):
        """Create the connectivity status widget."""
        frame = self._create_collapsible_section("Estado de la Conexión")

        frame.columnconfigure(1, weight=1)

        # Connection status
        ttk.Label(frame, text="Internet:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.conn_status_var = tk.StringVar(value="Verificando...")
        self.conn_status_label = ttk.Label(frame, textvariable=self.conn_status_var, font=("Segoe UI", 10, "bold"))
        self.conn_status_label.grid(row=0, column=1, sticky="w", padx=5, pady=2)

        # Current network
        ttk.Label(frame, text="Red Wi-Fi:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.conn_network_var = tk.StringVar(value="-")
        ttk.Label(frame, textvariable=self.conn_network_var).grid(row=1, column=1, sticky="w", padx=5, pady=2)

    def _build_device_list_widget(self):
        """Create the device list widget."""
        frame = self._create_collapsible_section(
            "Dispositivos Conectados",
            pady=(15, 5),
        )

        # Frame for the Treeview and scrollbar
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True)

        columns = ('name', 'serial_number', 'serial_port', 'baudrate', 'slave_id', 'tcp_ip', 'tcp_port', 'status' ,'logo_ip', 'logo_port', 'logo_status')
       
        self.device_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=5)
        self.device_tree.heading('name', text='Nombre')
        self.device_tree.heading('serial_number', text='Número de Serie')
        self.device_tree.heading('serial_port', text='Puerto Serial')
        self.device_tree.heading('baudrate', text='Baudrate')
        self.device_tree.heading('slave_id', text='Slave ID')
        self.device_tree.heading('tcp_ip', text='IP TCP')
        self.device_tree.heading('tcp_port', text='Puerto TCP')
        self.device_tree.heading('status', text='Estado TCP/Serial')
        self.device_tree.heading('logo_ip', text='IP LOGO!')
        self.device_tree.heading('logo_port', text='Puerto LOGO!')
        self.device_tree.heading('logo_status', text='Estado LOGO!')

        # Column widths adjusted to fit the window
        self.device_tree.column('name', width=80, stretch=tk.YES)
        self.device_tree.column('serial_number', width=120, stretch=tk.NO)
        self.device_tree.column('serial_port', width=110, anchor='center', stretch=tk.NO)
        self.device_tree.column('baudrate', width=80, anchor='center', stretch=tk.NO)
        self.device_tree.column('slave_id', width=70, anchor='center', stretch=tk.NO)
        self.device_tree.column('tcp_ip', width=120, anchor='center', stretch=tk.NO)
        self.device_tree.column('tcp_port', width=80, anchor='center', stretch=tk.NO)
        self.device_tree.column('logo_ip', width=120, anchor='center', stretch=tk.NO)
        self.device_tree.column('status', width=100, anchor='center', stretch=tk.NO)
        self.device_tree.column('logo_port', width=120, anchor='center', stretch=tk.NO)
        self.device_tree.column('logo_status', width=120, anchor='center', stretch=tk.NO)

        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.device_tree.yview)
        self.device_tree.configure(yscrollcommand=scrollbar.set)

        self.device_tree.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

    def _build_key_events_widget(self):
        """Show a concise, de-duplicated view of operational events."""
        frame = self._create_collapsible_section(
            "Eventos importantes",
            pady=(10, 5),
        )

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Label(
            toolbar,
            text="Conexiones, comandos, cambios de configuración y errores",
        ).pack(side="left")
        ttk.Button(
            toolbar,
            text="Limpiar",
            command=self._clear_key_events,
        ).pack(side="right")

        columns = ("time", "level", "message")
        self.key_events_tree = ttk.Treeview(
            frame,
            columns=columns,
            show="headings",
            height=6,
        )
        self.key_events_tree.heading("time", text="Hora")
        self.key_events_tree.heading("level", text="Tipo")
        self.key_events_tree.heading("message", text="Evento")
        self.key_events_tree.column("time", width=85, anchor="center", stretch=False)
        self.key_events_tree.column("level", width=105, anchor="center", stretch=False)
        self.key_events_tree.column("message", width=850, stretch=True)
        self.key_events_tree.tag_configure("error", foreground="#b71c1c")
        self.key_events_tree.tag_configure("warning", foreground="#a05a00")
        self.key_events_tree.tag_configure("success", foreground="#1b5e20")
        self.key_events_tree.tag_configure("info", foreground="#0d47a1")

        scrollbar = ttk.Scrollbar(
            frame,
            orient="vertical",
            command=self.key_events_tree.yview,
        )
        self.key_events_tree.configure(yscrollcommand=scrollbar.set)
        self.key_events_tree.pack(side="left", fill="x", expand=True)
        scrollbar.pack(side="right", fill="y")

    def update_device_list(self, devices):
        self._ui_queue.put(("devices", list(devices)))

    def _apply_device_list(self, devices):
        if not self.device_tree_tags_configured:
            self.device_tree.tag_configure('evenrow', background='#f0f0f0')
            self.device_tree.tag_configure('oddrow', background='#ffffff')
            self.device_tree_tags_configured = True
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        for index, device in enumerate(devices):
            cc = device.get("cc", {})
            self.device_tree.insert('', 'end', values=(
                device.get("name", "-"), device.get("serial", "-"),
                cc.get("serialPort", "-"), cc.get("baudrate", "-"), cc.get("slaveId", "-"),
                cc.get("host") if cc.get("host") not in (None, "-") else cc.get("tcpIp", "-"),
                cc.get("tcpPort", "-"), "Online" if device.get("connected") else "Offline",
                cc.get("logoIp", "-"), cc.get("logoPort", "-"),
                "Online" if device.get("connected_logo") else "Offline",
            ), tags=('evenrow' if index % 2 == 0 else 'oddrow',))

    def _save_gateway_config(self):
        if not self._service_available or self._save_pending:
            return
        organization_id = self.org_id_var.get().strip()
        gateway_id = self.gw_id_var.get().strip()
        if not organization_id or not gateway_id:
            messagebox.showerror("Datos requeridos", "Complete Organization ID y Gateway ID.")
            return
        self._save_pending = True
        self.save_button.configure(state="disabled")
        self.controller.save_gateway(organization_id, gateway_id)

    def _apply_runtime_snapshot(self, snapshot):
        self._service_available = True
        self._refresh_service_status()
        if not self._save_pending:
            self.save_button.configure(state="normal")
        gateway = snapshot["gateway"]
        identity = (gateway.get("organizationId", ""), gateway.get("gatewayId", ""))
        # Polling must not overwrite an edit that the user is still typing.
        if identity != self._gateway_identity:
            self.org_id_var.set(identity[0])
            self.gw_id_var.set(identity[1])
            self._gateway_identity = identity
        self._apply_device_list(snapshot["devices"])
        connectivity = snapshot["connectivity"]
        if connectivity["connected"] is None:
            self.conn_status_var.set("Verificando...")
            self.conn_network_var.set("-")
        else:
            self._apply_connectivity_status(connectivity["connected"], connectivity["network"])
        for entry in snapshot["logs"]:
            self._append_log(entry["message"])

    def _refresh_service_status(self):
        presentation = service_presentation(self._system_service, self._service_available)
        self.system_service_var.set(presentation['service'])
        self.system_service_label.configure(foreground=presentation['service_color'])
        self.startup_status_var.set(presentation['startup'])
        self.startup_status_label.configure(foreground=presentation['startup_color'])
        self.service_status_var.set(presentation['runtime'])
        self.service_status_label.configure(foreground=presentation['runtime_color'])
        self.service_hint_var.set(presentation['hint'])

    def _service_unavailable(self):
        self._service_available = False
        self.save_button.configure(state="disabled")
        self._refresh_service_status()
        self.conn_status_var.set("Sin datos del servicio")
        self.conn_status_label.config(foreground="#a05a00")
        self.conn_network_var.set("-")
        self._apply_device_list([])

    def _build_log_widget(self):
        """Create the text widget for logs."""
        widget = scrolledtext.ScrolledText(self, state="disabled", height=10)
        widget.pack(fill="x", padx=15, pady=(5, 15))
        return widget

    @staticmethod
    def _classify_key_event(message):
        normalized = message.lower()
        noisy_fragments = (
            "error polling ",
            "exception polling register",
            "error reading registers",
            "error en read_holding_registers",
            "excepción en read_holding_registers",
        )
        if any(fragment in normalized for fragment in noisy_fragments):
            return None

        if "❌" in message or any(
            word in normalized
            for word in ("error", "falló", "failed", "no se pudo", "missing")
        ):
            return "error"
        if "⚠" in message or any(
            word in normalized
            for word in ("desconect", "offline", "sin respuesta", "sin conexión")
        ):
            return "warning"
        if "✅" in message or any(
            word in normalized
            for word in ("connected", "online", "conexión establecida", "recuperada")
        ):
            return "success"
        if any(
            word in normalized
            for word in (
                "comando",
                "command-result",
                "mqtt-cmd",
                "intentando encender",
                "intentando apagar",
                "intentando reiniciar",
                "configuración",
                "reinici",
                "start modbus",
                "stop modbus",
                "gateway ejecutándose",
            )
        ):
            return "info"
        return None

    def _append_key_event(self, message, level):
        now = time.monotonic()
        dedupe_key = re.sub(
            r"reintento en \d+s",
            "reintento",
            message.lower(),
        )
        if now - self._last_key_events.get(dedupe_key, 0) < 15:
            return
        self._last_key_events[dedupe_key] = now

        labels = {
            "error": "Error",
            "warning": "Advertencia",
            "success": "Correcto",
            "info": "Información",
        }
        item = self.key_events_tree.insert(
            "",
            "end",
            values=(datetime.now().strftime("%H:%M:%S"), labels[level], message),
            tags=(level,),
        )
        self._key_event_ids.append(item)
        while len(self._key_event_ids) > 50:
            oldest = self._key_event_ids.pop(0)
            self.key_events_tree.delete(oldest)
        self.key_events_tree.see(item)

    def _clear_key_events(self):
        for item in self.key_events_tree.get_children():
            self.key_events_tree.delete(item)
        self._key_event_ids.clear()
        self._last_key_events.clear()

    def _append_log(self, message):
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", message + "\n")
        self.log_widget.configure(state="disabled")
        self.log_widget.yview("end")

        level = self._classify_key_event(message)
        if level:
            self._append_key_event(message, level)

    def _log(self, message):
        self._ui_queue.put(("log", str(message)))

    def _apply_connectivity_status(self, is_connected, network_name):
        """Update the UI with the internet connection status."""
        if is_connected:
            self.conn_status_var.set("Conectado")
            self.conn_status_label.config(foreground="green")
            self.conn_network_var.set(network_name)
        else:
            self.conn_status_var.set("Desconectado")
            self.conn_status_label.config(foreground="red")
            self.conn_network_var.set(network_name)

    def update_connectivity_status(self, is_connected: bool, network_name: str):
        self._ui_queue.put(
            ("connectivity", (is_connected, network_name))
        )

    def _drain_ui_queue(self):
        try:
            while True:
                event, payload = self._ui_queue.get_nowait()
                if event == "runtime":
                    self._apply_runtime_snapshot(payload)
                elif event == 'system_service':
                    self._system_service = payload
                    self._refresh_service_status()
                elif event == "service_unavailable":
                    self._service_unavailable()
                    self._append_log("⚠️ Servicio no disponible. La interfaz seguirá intentando conectarse.")
                elif event == "save_result":
                    self._save_pending = False
                    if payload is not None:
                        self.save_button.configure(state="normal" if self._service_available else "disabled")
                        messagebox.showerror("No se pudo guardar", payload)
                    else:
                        self._service_unavailable()
                        self._append_log("Configuración guardada. Esperando el reinicio del servicio…")
                elif event == "log":
                    self._append_log(payload)
                elif event == "connectivity":
                    self._apply_connectivity_status(*payload)
                elif event == "devices":
                    self._apply_device_list(payload)
        except queue.Empty:
            pass
        self.after(100, self._drain_ui_queue)

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()
