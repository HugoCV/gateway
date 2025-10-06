import tkinter as tk
from tkinter import ttk, scrolledtext
from application.app_controller import AppController
# from infrastructure.modbus.modbus_tcp import ModbusTcp
# from infrastructure.http.http_client import HttpClient
from infrastructure.mqtt.mqtt_client import MQTT_HOST, MQTT_PORT

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
        self.style.configure("TCombobox", font=("Segoe UI", 10))
        self.style.map("TButton",
            background=[("active", "#d9d9d9"), ("pressed", "#c0c0c0")],
            foreground=[("disabled", "#999")]
        )
        self.style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

        # Tags para colores en el Treeview
        self.style.configure("Treeview",
            background="#ffffff",
            fieldbackground="#ffffff",
            rowheight=25
        )
        self.style.map("Treeview", background=[('selected', '#0078D7')])

        self.device_tree_tags_configured = False


        self._build_gateway_config_widget()
        self._build_device_list_widget()
        self.log_widget = self._build_log_widget()
        self.controller = AppController(self)

    def _build_gateway_config_widget(self):
        frame = ttk.LabelFrame(self, text="Configuración de Gateway", padding=15)
        frame.pack(fill="x", padx=15, pady=(15, 5))

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
        # El command se asignará en el controller
        save_button = ttk.Button(frame, text="Guardar y Reiniciar", command=lambda: self.controller.on_save_gateway_config())
        save_button.grid(row=2, column=1, sticky="e", padx=5, pady=10)

    def _build_device_list_widget(self):
        frame = ttk.LabelFrame(self, text="Dispositivos Conectados", padding=15)
        frame.pack(fill="x", padx=15, pady=(15, 5))

        # Frame para el Treeview y el Scrollbar
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

        # Ajuste de anchos de columna para que quepan en la ventana
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

    def update_device_list(self, devices):
        if not self.device_tree_tags_configured:
            # Configurar tags de colores la primera vez
            self.device_tree.tag_configure('online', foreground='green')
            self.device_tree.tag_configure('offline', foreground='red')
            self.device_tree.tag_configure('evenrow', background='#f0f0f0')
            self.device_tree.tag_configure('oddrow', background='#ffffff')
            self.device_tree_tags_configured = True

        # Limpiar la tabla antes de actualizar
        for i in self.device_tree.get_children():
            self.device_tree.delete(i)

        # Llenar con los nuevos datos
        for i, device in enumerate(devices):
            row_tag = 'evenrow' if i % 2 == 0 else 'oddrow'
            tcp_ip = device.cc.get("tcpIp", "-")
            tcp_port = device.cc.get("tcpPort", "-")
            logo_ip = device.cc.get("logoIp", "-")
            serial_port = device.cc.get("serialPort", "-")
            baudrate = device.cc.get("baudrate", "-")
            slave_id = device.cc.get("slaveId", "-")
            logo_port = device.cc.get("logoPort", "-")
            status_text = "Online" if device.connected else "Offline"
            logo_status_text = "Online" if device.connected_logo else "Offline"

            # Insertar valores y aplicar tags
            item_id = self.device_tree.insert('', 'end', values=(device.name, device.serial, serial_port, baudrate, slave_id, tcp_ip, tcp_port, status_text, logo_ip, logo_port, logo_status_text), tags=(row_tag,))
            
            # Aplicar tags de color solo a las celdas de estado (esto requiere un workaround en Tkinter)
            # La forma estándar de colorear celdas no existe, pero podemos re-insertar con tags.
            # Esta implementación es más simple y colorea toda la fila, lo cual es aceptado.

    def _build_log_widget(self):
        widget = scrolledtext.ScrolledText(self, state="disabled", height=10)
        widget.pack(fill="x", padx=15, pady=(5, 15))
        return widget

    def _log(self, message):
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", message + "\n")
        self.log_widget.configure(state="disabled")
        self.log_widget.yview("end")

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()
