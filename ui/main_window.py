import tkinter as tk
import json
import queue
import re
import sys
import time
from datetime import datetime
from tkinter import ttk, scrolledtext, messagebox
from ui.service_client import ServiceClient
from ui.service_status import service_presentation


BACKGROUND = "#151b22"
PANEL = "#202a35"
TABLE = "#1a232d"
TABLE_ALT = "#202b36"
TEXT = "#edf3f8"
MUTED = "#a8b5c2"
ACCENT = "#62c4e9"
SUCCESS = "#76d69c"
WARNING = "#ffb56b"
ERROR = "#ff8d8d"
FONT = "Helvetica Neue" if sys.platform == "darwin" else "Segoe UI"

class MainWindow(tk.Tk):
    def __init__(self, client=None, read_only=False, title=None):
        super().__init__()
        self._read_only = read_only
        self.title(title or "Puerta de enlace")
        self.geometry("1050x760")
        self.minsize(820, 600)
        self.configure(background=BACKGROUND)

        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TFrame", background=BACKGROUND)
        self.style.configure("Card.TFrame", background=PANEL)
        self.style.configure("TLabel", font=(FONT, 11), background=BACKGROUND, foreground=TEXT)
        self.style.configure("Card.TLabel", background=PANEL, foreground=TEXT)
        self.style.configure("Muted.Card.TLabel", background=PANEL, foreground=MUTED)
        self.style.configure("Title.Card.TLabel", font=(FONT, 19, "bold"), background=PANEL, foreground=TEXT)
        self.style.configure("Status.Card.TLabel", font=(FONT, 11, "bold"), background=PANEL, foreground=SUCCESS)
        self.style.configure("TEntry", font=(FONT, 11), padding=6,
                             fieldbackground=TABLE, foreground=TEXT, bordercolor="#425162")
        self.style.configure("TButton", font=(FONT, 11), padding=7,
                             background="#344354", foreground=TEXT, borderwidth=0)
        self.style.configure(
            "Section.TButton",
            font=(FONT, 12, "bold"),
            padding=(16, 11),
            anchor="w",
            background=PANEL,
            foreground=TEXT,
            borderwidth=0,
        )
        self.style.configure("TCombobox", font=(FONT, 11))
        self.style.map("TButton",
            background=[("active", "#42576d"), ("pressed", "#30485e")],
            foreground=[("disabled", MUTED)]
        )
        self.style.map("Section.TButton", background=[("active", "#2c3b4b")])
        self.style.configure("Treeview.Heading", font=(FONT, 10, "bold"),
                             background="#324456", foreground=TEXT, padding=8)

        # Treeview color tags
        self.style.configure("Treeview",
            font=(FONT, 10), background=TABLE, foreground=TEXT,
            fieldbackground=TABLE, rowheight=29, borderwidth=0
        )
        self.style.map("Treeview", background=[('selected', '#245a78')],
                       foreground=[('selected', TEXT)])
        self.style.configure("Vertical.TScrollbar", background="#344354",
                             troughcolor=TABLE, arrowcolor=MUTED,
                             bordercolor=PANEL, lightcolor="#344354",
                             darkcolor="#344354")

        self.device_tree_tags_configured = False
        self._collapsible_sections = []
        self._key_event_ids = []
        self._last_key_events = {}
        self._ui_queue = queue.Queue()
        self._gateway_identity = None
        self._service_available = False
        self._save_pending = False
        self._system_service = {}
        self._build_scrollable_content()
        header = ttk.Frame(self._content, style="Card.TFrame", padding=(18, 14))
        header.pack(fill="x", padx=18, pady=(18, 16))
        ttk.Label(header, text="Puerta de enlace", style="Title.Card.TLabel").pack(anchor="w")
        self.system_service_var = tk.StringVar()
        self.system_service_label = ttk.Label(header, textvariable=self.system_service_var,
                                              style="Muted.Card.TLabel")
        self.system_service_label.pack(anchor="w", pady=(4, 0))
        self.startup_status_var = tk.StringVar()
        self.startup_status_label = ttk.Label(header, textvariable=self.startup_status_var,
                                              style="Muted.Card.TLabel")
        self.startup_status_label.pack(anchor="w")
        self.service_status_var = tk.StringVar()
        self.service_status_label = ttk.Label(header, textvariable=self.service_status_var,
                                              style="Status.Card.TLabel")
        self.service_status_label.pack(anchor="w", pady=(7, 0))
        self.service_hint_var = tk.StringVar()
        ttk.Label(header, textvariable=self.service_hint_var,
                  style="Muted.Card.TLabel", wraplength=900).pack(anchor="w", pady=(3, 0))
        self._refresh_service_status()

        self._build_connectivity_widget()
        self._build_device_list_widget()
        self._build_signals_widget()
        self._build_key_events_widget()
        self.log_widget = self._build_log_widget()
        self._build_gateway_config_widget()
        self.after(100, self._drain_ui_queue)
        self.controller = ServiceClient(self._ui_queue, client=client)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_scrollable_content(self):
        self._canvas = tk.Canvas(self, background=BACKGROUND, highlightthickness=0,
                                 borderwidth=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._content = ttk.Frame(self._canvas, style="TFrame")
        content_id = self._canvas.create_window((0, 0), window=self._content, anchor="nw")
        self._content.bind(
            "<Configure>",
            lambda _event: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas.bind(
            "<Configure>",
            lambda event: self._canvas.itemconfigure(content_id, width=event.width),
        )
        self.bind("<MouseWheel>", self._scroll_content, add="+")
        self.bind("<Button-4>", self._scroll_content, add="+")
        self.bind("<Button-5>", self._scroll_content, add="+")

    def _scroll_content(self, event):
        if isinstance(event.widget, (ttk.Treeview, tk.Text)):
            return
        if getattr(event, "num", None) == 4:
            direction = -1
        elif getattr(event, "num", None) == 5:
            direction = 1
        else:
            delta = event.delta
            direction = -int(delta / 120) if abs(delta) >= 120 else -int(delta)
        if direction:
            self._canvas.yview_scroll(direction, "units")

    def _close(self):
        """Disconnect this window without stopping the service or its devices."""
        if hasattr(self, "controller"):
            self.controller.close()
        self.destroy()

    def _create_collapsible_section(self, title, expanded_by_default=False):
        """Create a section whose contents are hidden until its header is clicked."""
        container = ttk.Frame(self._content, style="Card.TFrame")
        container.pack(fill="x", padx=18, pady=(0, 9))

        body = ttk.Frame(container, style="Card.TFrame", padding=(16, 0, 16, 15))
        expanded = tk.BooleanVar(value=expanded_by_default)
        title_var = tk.StringVar(value=f"{'▼' if expanded_by_default else '▶'}  {title}")

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
        if expanded_by_default:
            body.pack(fill="x")
        self._collapsible_sections.append((container, header, body, expanded))
        return body

    def _build_gateway_config_widget(self):
        """Create the gateway configuration widget."""
        frame = self._create_collapsible_section("Identidad del Gateway")

        frame.columnconfigure(1, weight=1)

        # Organization ID
        ttk.Label(frame, text="Organization ID:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.org_id_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.org_id_var,
                  state="readonly" if self._read_only else "normal").grid(
                      row=0, column=1, sticky="ew", padx=5, pady=5)

        # Gateway ID
        ttk.Label(frame, text="Gateway ID:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.gw_id_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.gw_id_var,
                  state="readonly" if self._read_only else "normal").grid(
                      row=1, column=1, sticky="ew", padx=5, pady=5)

        # Save Button
        self.save_button = ttk.Button(frame, text="Solo lectura" if self._read_only else "Guardar y reiniciar servicio",
                                      command=self._save_gateway_config, state="disabled")
        self.save_button.grid(row=2, column=1, sticky="e", padx=5, pady=10)

    def _build_connectivity_widget(self):
        """Create the connectivity status widget."""
        frame = self._create_collapsible_section("Conectividad", expanded_by_default=True)

        frame.columnconfigure(1, weight=1)

        # Connection status
        ttk.Label(frame, text="Internet (sondeo):", style="Muted.Card.TLabel").grid(
            row=0, column=0, sticky="w", padx=5, pady=3)
        self.conn_status_var = tk.StringVar(value="Verificando...")
        self.conn_status_label = ttk.Label(frame, textvariable=self.conn_status_var,
                                           style="Status.Card.TLabel")
        self.conn_status_label.grid(row=0, column=1, sticky="w", padx=5, pady=2)

        # Current network
        ttk.Label(frame, text="Red Wi-Fi:", style="Muted.Card.TLabel").grid(
            row=1, column=0, sticky="w", padx=5, pady=3)
        self.conn_network_var = tk.StringVar(value="-")
        ttk.Label(frame, textvariable=self.conn_network_var, style="Card.TLabel").grid(
            row=1, column=1, sticky="w", padx=5, pady=3)
        if self._read_only:
            ttk.Label(frame, text="El sondeo a 8.8.8.8 no mide MQTT ni el estado de los dispositivos.",
                      style="Muted.Card.TLabel").grid(row=2, column=0, columnspan=2,
                                                        sticky="w", padx=5, pady=(8, 0))

    def _build_device_list_widget(self):
        """Create the device list widget."""
        frame = self._create_collapsible_section("Dispositivos", expanded_by_default=True)

        # Frame for the Treeview and scrollbar
        tree_frame = ttk.Frame(frame, style="Card.TFrame")
        tree_frame.pack(fill="both", expand=True)

        columns = ('name', 'serial_number', 'channels', 'status')
       
        self.device_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=5)
        self.device_tree.heading('name', text='Nombre')
        self.device_tree.heading('serial_number', text='Número de Serie')
        self.device_tree.heading('channels', text='Canales de comunicación')
        self.device_tree.heading('status', text='Estado general')

        # Column widths adjusted to fit the window
        self.device_tree.column('name', width=80, stretch=tk.YES)
        self.device_tree.column('serial_number', width=120, stretch=tk.NO)
        self.device_tree.column('channels', width=450, anchor='w', stretch=tk.YES)
        self.device_tree.column('status', width=100, anchor='center', stretch=tk.NO)

        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.device_tree.yview)
        self.device_tree.configure(yscrollcommand=scrollbar.set)

        self.device_tree.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

    def _build_signals_widget(self):
        """Show the last MQTT publication for each configured Modbus signal."""
        frame = self._create_collapsible_section("Señales enviadas", expanded_by_default=True)
        self._signal_rows = {}
        self._last_signal_publications = None

        self.signal_summary_var = tk.StringVar(value="Esperando el primer envío de señales…")
        ttk.Label(frame, textvariable=self.signal_summary_var,
                  style="Muted.Card.TLabel").pack(anchor="w", pady=(0, 9))

        table_frame = ttk.Frame(frame, style="Card.TFrame")
        table_frame.pack(fill="x")
        columns = ("device", "channel", "signal", "address", "value", "time", "delivery")
        self.signal_tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", height=5,
        )
        for column, title in (
            ("device", "Dispositivo"),
            ("channel", "Canal"),
            ("signal", "Señal"),
            ("address", "Dirección Modbus"),
            ("value", "Valor enviado"),
            ("time", "Hora"),
            ("delivery", "Entrega"),
        ):
            self.signal_tree.heading(column, text=title)
        for column, width, stretch in (
            ("device", 135, True), ("channel", 130, True),
            ("signal", 175, True), ("address", 120, False), ("value", 120, True),
            ("time", 80, False), ("delivery", 110, False),
        ):
            self.signal_tree.column(column, width=width, stretch=stretch,
                                    anchor="center" if column in {"address", "time", "delivery"} else "w")
        self.signal_tree.tag_configure("evenrow", background=TABLE, foreground=TEXT)
        self.signal_tree.tag_configure("oddrow", background=TABLE_ALT, foreground=TEXT)
        self.signal_tree.tag_configure("failed", foreground=ERROR)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.signal_tree.yview)
        self.signal_tree.configure(yscrollcommand=scrollbar.set)
        self.signal_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.signal_tree.bind("<<TreeviewSelect>>", self._on_signal_selection)

        self.signal_topic_var = tk.StringVar(value="Destino MQTT: —")
        ttk.Label(frame, textvariable=self.signal_topic_var,
                  style="Muted.Card.TLabel", wraplength=750).pack(anchor="w", pady=(9, 0))

    @staticmethod
    def _format_signal_value(value):
        if value is None:
            return "—"
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, default=str)[:100]
        return str(value)[:100]

    def _apply_signal_publications(self, publications):
        if publications == self._last_signal_publications:
            return
        self._last_signal_publications = publications
        selected = self.signal_tree.selection()
        selected_key = self._signal_rows.get(selected[0], {}).get("key") if selected else None
        for row in self.signal_tree.get_children():
            self.signal_tree.delete(row)
        self._signal_rows = {}

        rows = []
        for publication in publications:
            sent_at = publication.get("sentAt")
            try:
                time_label = datetime.fromtimestamp(float(sent_at)).strftime("%H:%M:%S")
            except (TypeError, ValueError, OverflowError, OSError):
                time_label = "—"
            delivery = {
                "confirmed": "Confirmado",
                "unconfirmed": "Sin confirmar",
                "failed": "No enviado",
            }.get(publication.get("delivery"), "Desconocido")
            for signal in publication.get("signals", []):
                key = (publication.get("serial"), publication.get("channelId"), signal.get("id"))
                rows.append((key, publication.get("topic", ""), (
                    publication.get("deviceName") or publication.get("serial") or "—",
                    publication.get("channelName") or publication.get("channelId") or "—",
                    "{} ({})".format(signal.get("name") or signal.get("id") or "—",
                                     signal.get("id") or "—"),
                    signal.get("address") if signal.get("address") is not None else "—",
                    self._format_signal_value(signal.get("value")), time_label, delivery,
                ), delivery))

        for index, (key, topic, values, delivery) in enumerate(rows):
            tag = "failed" if delivery == "No enviado" else (
                "evenrow" if index % 2 == 0 else "oddrow")
            item = self.signal_tree.insert("", "end", values=values, tags=(tag,))
            self._signal_rows[item] = {"key": key, "topic": topic}
            if key == selected_key:
                self.signal_tree.selection_set(item)

        self.signal_tree.configure(height=max(1, min(6, len(rows))))

        if rows:
            latest = rows[0][2][5]
            latest_label = "Último intento" if publications[0].get("delivery") == "failed" else "Último envío"
            omitted = sum(publication.get("omitted", 0) for publication in publications)
            extra = f" · {omitted} señales omitidas del visor" if omitted else ""
            self.signal_summary_var.set(
                f"{latest_label}: {latest} · {len(rows)} señales · "
                f"{len(publications)} canal(es){extra}"
            )
            if not self.signal_tree.selection():
                self.signal_tree.selection_set(self.signal_tree.get_children()[0])
            self._on_signal_selection()
        else:
            self.signal_summary_var.set("Esperando el primer envío de señales…")
            self.signal_topic_var.set("Destino MQTT: —")

    def _on_signal_selection(self, _event=None):
        selected = self.signal_tree.selection()
        row = self._signal_rows.get(selected[0]) if selected else None
        self.signal_topic_var.set(
            f"Destino MQTT: {row['topic']}" if row else "Destino MQTT: —"
        )

    def _build_key_events_widget(self):
        """Show a concise, de-duplicated view of operational events."""
        frame = self._create_collapsible_section("Eventos importantes")

        toolbar = ttk.Frame(frame, style="Card.TFrame")
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Label(
            toolbar,
            text="Conexiones, comandos, cambios de configuración y errores",
            style="Muted.Card.TLabel",
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
        self.key_events_tree.tag_configure("error", foreground=ERROR)
        self.key_events_tree.tag_configure("warning", foreground=WARNING)
        self.key_events_tree.tag_configure("success", foreground=SUCCESS)
        self.key_events_tree.tag_configure("info", foreground=ACCENT)

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
            self.device_tree.tag_configure('evenrow', background=TABLE, foreground=TEXT)
            self.device_tree.tag_configure('oddrow', background=TABLE_ALT, foreground=TEXT)
            self.device_tree_tags_configured = True
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        for index, device in enumerate(devices):
            channels = ", ".join(
                f"{channel.get('name') or channel['id']}: "
                f"{'Online' if channel.get('connected') is True else 'Offline' if channel.get('connected') is False else 'Conectando'}"
                for channel in device.get("channels", [])
            ) or "—"
            self.device_tree.insert('', 'end', values=(
                device.get("name", "-"), device.get("serial", "-"),
                channels, "Online" if device.get("connected") else "Offline",
            ), tags=('evenrow' if index % 2 == 0 else 'oddrow',))
        self.device_tree.configure(height=max(1, min(5, len(devices))))

    def _save_gateway_config(self):
        if self._read_only or not self._service_available or self._save_pending:
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
        if not self._read_only and not self._save_pending:
            self.save_button.configure(state="normal")
        gateway = snapshot["gateway"]
        identity = (gateway.get("organizationId", ""), gateway.get("gatewayId", ""))
        # Polling must not overwrite an edit that the user is still typing.
        if identity != self._gateway_identity:
            self.org_id_var.set(identity[0])
            self.gw_id_var.set(identity[1])
            self._gateway_identity = identity
        self._apply_device_list(snapshot["devices"])
        self._apply_signal_publications(snapshot.get("signalPublications", []))
        connectivity = snapshot["connectivity"]
        if connectivity["connected"] is None:
            self.conn_status_var.set("Verificando...")
            self.conn_network_var.set("-")
        else:
            self._apply_connectivity_status(connectivity["connected"], connectivity["network"])
        for entry in snapshot["logs"]:
            self._append_log(entry["message"])

    def _refresh_service_status(self):
        if self._read_only:
            self.system_service_var.set("Visor de Docker · solo lectura")
            self.startup_status_var.set("El motor permanece dentro del contenedor")
            self.service_status_var.set(
                "Gateway conectado · responde a la ventana" if self._service_available
                else "Gateway sin respuesta · reconexión automática")
            self.service_status_label.configure(
                foreground=SUCCESS if self._service_available else WARNING)
            self.service_hint_var.set("Cerrar esta ventana no detiene el contenedor.")
            return
        presentation = service_presentation(self._system_service, self._service_available)
        self.system_service_var.set(presentation['service'])
        self.system_service_label.configure(foreground=(
            SUCCESS if self._system_service.get('active') == 'active' else MUTED))
        self.startup_status_var.set(presentation['startup'])
        self.startup_status_label.configure(foreground=MUTED)
        self.service_status_var.set(presentation['runtime'])
        self.service_status_label.configure(
            foreground=SUCCESS if self._service_available else WARNING)
        self.service_hint_var.set(presentation['hint'])

    def _service_unavailable(self):
        self._service_available = False
        self.save_button.configure(state="disabled")
        self._refresh_service_status()
        self.conn_status_var.set("Sin datos del servicio")
        self.conn_status_label.config(foreground="#a05a00")
        self.conn_network_var.set("-")
        self._apply_device_list([])
        self._apply_signal_publications([])

    def _build_log_widget(self):
        """Create the text widget for logs."""
        frame = self._create_collapsible_section("Registro técnico")
        widget = scrolledtext.ScrolledText(
            frame, state="disabled", height=10, background=TABLE,
            foreground=TEXT, insertbackground=TEXT, font=("Menlo", 10),
            relief="flat", borderwidth=0, wrap="word",
        )
        widget.pack(fill="x")
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
            self.conn_status_label.config(foreground=SUCCESS)
            self.conn_network_var.set(network_name)
        else:
            self.conn_status_var.set("Sin respuesta" if self._read_only else "Desconectado")
            self.conn_status_label.config(foreground=WARNING if self._read_only else ERROR)
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
                        self.save_button.configure(
                            state="normal" if self._service_available and not self._read_only else "disabled")
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
