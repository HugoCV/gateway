import tkinter as tk
from tkinter import ttk, scrolledtext, simpledialog
from tkinter import messagebox
from typing import Dict
from application.app_controller import AppController
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
        self._build_connectivity_widget()
        self._build_known_networks_widget()
        self._build_device_list_widget()
        self.log_widget = self._build_log_widget()
        self.controller = AppController(self)

    def _build_gateway_config_widget(self):
        """Crea el widget para la configuración del gateway."""
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
        save_button = ttk.Button(frame, text="Guardar y Reiniciar", command=lambda: self.controller.on_save_gateway_config())
        save_button.grid(row=2, column=1, sticky="e", padx=5, pady=10)

    def _build_connectivity_widget(self):
        """Crea el widget para mostrar el estado de la conectividad."""
        frame = ttk.LabelFrame(self, text="Estado de la Conexión", padding=15)
        frame.pack(fill="x", padx=15, pady=5)

        frame.columnconfigure(1, weight=1)

        # Connection Status
        ttk.Label(frame, text="Internet:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.conn_status_var = tk.StringVar(value="Verificando...")
        self.conn_status_label = ttk.Label(frame, textvariable=self.conn_status_var, font=("Segoe UI", 10, "bold"))
        self.conn_status_label.grid(row=0, column=1, sticky="w", padx=5, pady=2)

        # Actual Network
        ttk.Label(frame, text="Red Wi-Fi:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.conn_network_var = tk.StringVar(value="-")
        ttk.Label(frame, textvariable=self.conn_network_var).grid(row=1, column=1, sticky="w", padx=5, pady=2)

    def _build_known_networks_widget(self):
        """Crea el widget para gestionar las redes Wi-Fi conocidas."""
        frame = ttk.LabelFrame(self, text="Redes Wi-Fi Conocidas (Guardado automático)", padding=15)
        frame.pack(fill="x", padx=15, pady=5)

        # Treeview to show networks
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="x", expand=True, pady=(0, 10))
        
        self.network_tree = ttk.Treeview(tree_frame, columns=('ssid', 'password'), show='headings', height=3)
        self.network_tree.heading('ssid', text='Nombre de Red (SSID)')
        self.network_tree.heading('password', text='Contraseña')
        self.network_tree.column('ssid', width=200)
        self.network_tree.column('password', width=200)
        self.network_tree.pack(side="left", fill="x", expand=True)

        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.network_tree.yview)
        self.network_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        button_frame = ttk.Frame(frame)
        button_frame.pack(fill="x")

        add_button = ttk.Button(button_frame, text="Añadir", command=self._add_network_dialog)
        add_button.pack(side="left", padx=5)

        edit_button = ttk.Button(button_frame, text="Editar", command=lambda: self._edit_network_dialog)
        edit_button.pack(side="left", padx=5)

        remove_button = ttk.Button(button_frame, text="Eliminar", command=self._remove_network)
        remove_button.pack(side="left", padx=5)

    def _edit_network(self, edit=False):
        selected_item = self.network_tree.selection()
        if not selected_item:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona una red para editar.")
            return
        item_values = self.network_tree.item(selected_item[0], 'values')
        ssid = item_values[0]


    def _add_network_dialog(self, edit=False):
        """Abre un diálogo para añadir o editar una red Wi-Fi."""
        ssid, password = "", ""
        dialog = NetworkDialog(self, title="Editar Red" if edit else "Añadir Red", ssid_initial=ssid, password_initial="")
        if dialog.result:
            new_ssid, new_password = dialog.result
            if edit:
                self.controller.on_edit_network(ssid, new_ssid, new_password)
            else:
                self.controller.on_add_network(new_ssid, new_password)

    def _remove_network(self):
        """Elimina la red seleccionada de la lista."""
        selected_item = self.network_tree.selection()
        if not selected_item:
            messagebox.showwarning("Selección requerida", "Por favor, selecciona una red para eliminar.")
            return
        
        ssid = self.network_tree.item(selected_item[0], 'values')[0]
        if messagebox.askyesno("Confirmar eliminación", f"¿Estás seguro de que quieres eliminar la red '{ssid}'?"):
            self.controller.on_remove_network(ssid)

    def update_known_networks_list(self, networks: Dict[str, str]):
        """Actualiza la lista de redes conocidas en la UI."""
        for i in self.network_tree.get_children():
            self.network_tree.delete(i)
        for ssid, password in networks.items():
            self.network_tree.insert('', 'end', values=(ssid, password))

    def _build_device_list_widget(self):
        """Crea el widget con la lista de dispositivos."""
        frame = ttk.LabelFrame(self, text="Dispositivos Conectados", padding=15)
        frame.pack(fill="x", padx=15, pady=(15, 5))

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
            self.device_tree.tag_configure('online', foreground='green')
            self.device_tree.tag_configure('offline', foreground='red')
            self.device_tree.tag_configure('evenrow', background='#f0f0f0')
            self.device_tree.tag_configure('oddrow', background='#ffffff')
            self.device_tree_tags_configured = True

        for i in self.device_tree.get_children():
            self.device_tree.delete(i)

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

            item_id = self.device_tree.insert('', 'end', values=(device.name, device.serial, serial_port, baudrate, slave_id, tcp_ip, tcp_port, status_text, logo_ip, logo_port, logo_status_text), tags=(row_tag,))
            

    def _build_log_widget(self):
        """Crea el widget de texto para los logs."""
        widget = scrolledtext.ScrolledText(self, state="disabled", height=10)
        widget.pack(fill="x", padx=15, pady=(5, 15))
        return widget

    def _log(self, message):
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", message + "\n")
        self.log_widget.configure(state="disabled")
        self.log_widget.yview("end")

    def update_connectivity_status(self, is_connected: bool, network_name: str):
        """Actualiza la UI con el estado de la conexión a Internet."""
        if is_connected:
            self.conn_status_var.set("Conectado")
            self.conn_status_label.config(foreground="green")
            self.conn_network_var.set(network_name)
        else:
            self.conn_status_var.set("Desconectado")
            self.conn_status_label.config(foreground="red")
            self.conn_network_var.set(network_name)

class NetworkDialog(simpledialog.Dialog):
    """Diálogo personalizado para añadir/editar redes Wi-Fi."""
    def __init__(self, parent, title=None, ssid_initial="", password_initial=""):
        self.ssid_initial = ssid_initial
        self.password_initial = password_initial
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text="Nombre de Red (SSID):").grid(row=0, sticky="w", padx=5, pady=5)
        self.ssid_entry = ttk.Entry(master, width=30)
        self.ssid_entry.grid(row=1, padx=5)
        self.ssid_entry.insert(0, self.ssid_initial)

        ttk.Label(master, text="Contraseña:").grid(row=2, sticky="w", padx=5, pady=5)
        self.password_entry = ttk.Entry(master, show="*", width=30)
        self.password_entry.grid(row=3, padx=5)
        self.password_entry.insert(0, self.password_initial)

        return self.ssid_entry

    def apply(self):
        ssid = self.ssid_entry.get().strip()
        password = self.password_entry.get()

        if not ssid:
            messagebox.showerror("Error de validación", "El nombre de la red (SSID) no puede estar vacío.", parent=self)
            self.result = None
            return

        if not password:
            if messagebox.askyesno("Sin Contraseña", "La contraseña está vacía. ¿Es una red abierta?", parent=self):
                 self.result = (ssid, "")
            else:
                self.result = None 
            return

        self.result = (ssid, password)

    def buttonbox(self):
        box = ttk.Frame(self)
        ttk.Button(box, text="OK", width=10, command=self.ok, default=tk.ACTIVE).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(box, text="Cancelar", width=10, command=self.cancel).pack(side=tk.LEFT, padx=5, pady=5)
        self.bind("<Return>", self.ok)
        box.pack()

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()
