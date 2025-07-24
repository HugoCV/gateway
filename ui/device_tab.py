import tkinter as tk
from tkinter import ttk
from config.loader import get_devices
def build_device_tab(app, parent):
    """
    Build the Devices configuration tab.
    `app` is the main App instance so we can access its methods and variables.
    `parent` is the tab frame inside the notebook.
    """

    # Lista de dispositivos simulada
    app.available_devices = get_devices()

    devices_frame = tk.LabelFrame(parent, text="Devices", padx=10, pady=10)
    devices_frame.pack(fill="x", padx=10, pady=10)

    # Combobox para seleccionar dispositivo
    tk.Label(devices_frame, text="Seleccionar dispositivo:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
    app.selected_device_var = tk.StringVar()
    device_names = [d["name"] for d in app.available_devices]
    app.device_combo = ttk.Combobox(devices_frame, textvariable=app.selected_device_var, values=device_names, state="readonly")
    app.device_combo.grid(row=0, column=1, sticky="we", padx=5, pady=5)

    def on_device_selected(event):
        selected_name = app.selected_device_var.get()
        # Buscar el dispositivo
        for d in app.available_devices:
            if d["name"] == selected_name:
                # Rellenar los campos
                app.device_name_var.set(d["name"])
                app.serial_var.set(d["serialNumber"])
                app.model_var.set(d["model"])
                app.device_ip.set(d["ip_address"])
                app.device_port.set(d["ip_port"])
                break

    app.device_combo.bind("<<ComboboxSelected>>", on_device_selected)

    # Device Name
    tk.Label(devices_frame, text="Nombre:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
    app.device_name_var = tk.StringVar()
    tk.Entry(devices_frame, textvariable=app.device_name_var).grid(row=1, column=1, sticky="we", padx=5, pady=5)

    # Serial Number
    tk.Label(devices_frame, text="Serial:").grid(row=2, column=0, sticky="e", padx=5, pady=5)
    app.serial_var = tk.StringVar()
    tk.Entry(devices_frame, textvariable=app.serial_var).grid(row=2, column=1, sticky="we", padx=5, pady=5)

    # Model
    tk.Label(devices_frame, text="Modelo:").grid(row=3, column=0, sticky="e", padx=5, pady=5)
    app.model_var = tk.StringVar()
    tk.Entry(devices_frame, textvariable=app.model_var).grid(row=3, column=1, sticky="we", padx=5, pady=5)

    # Device IP
    tk.Label(devices_frame, text="IP:").grid(row=4, column=0, sticky="e", padx=5, pady=5)
    app.device_ip  = tk.StringVar()
    tk.Entry(devices_frame, textvariable=app.device_ip).grid(row=4, column=1, sticky="we", padx=5, pady=5)

    # Port
    tk.Label(devices_frame, text="Puerto:").grid(row=5, column=0, sticky="e", padx=5, pady=5)
    app.device_port  = tk.StringVar()
    tk.Entry(devices_frame, textvariable=app.device_port).grid(row=5, column=1, sticky="we", padx=5, pady=5)

    # Device
    buttons_frame = tk.Frame(devices_frame)
    buttons_frame.grid(row=6, column=0, columnspan=2, pady=10)

    tk.Button(buttons_frame, text="Conectar", command=app._on_connect_device).pack(side="left", padx=5)
    tk.Button(buttons_frame, text="Encender", command=app._on_start_device).pack(side="left", padx=5)
    tk.Button(buttons_frame, text="Apagar", command=app._on_stop_device).pack(side="left", padx=5)

    #Save
    buttons_frame = tk.Frame(devices_frame)
    buttons_frame.grid(row=7, column=0, columnspan=2, pady=10)

    tk.Button(buttons_frame, text="Nuevo", command=app._on_save_device).pack(side="left", padx=5)
    tk.Button(buttons_frame, text="Agregar Dispositivo", command=app._on_start_device).pack(side="left", padx=5)
    tk.Button(buttons_frame, text="Eliminar", command=app._on_stop_device).pack(side="left", padx=5)

    devices_frame.columnconfigure(1, weight=1)
