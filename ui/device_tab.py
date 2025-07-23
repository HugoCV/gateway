# ui/devices_tab.py
import tkinter as tk

def build_device_tab(app, parent):
    """
    Build the Devices configuration tab.
    `app` is the main App instance so we can access its methods and variables.
    `parent` is the tab frame inside the notebook.
    """

    devices_frame = tk.LabelFrame(parent, text="Devices", padx=10, pady=10)
    devices_frame.pack(fill="x", padx=10, pady=10)

    # Device Name
    tk.Label(devices_frame, text="Nombre:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
    app.device_name_var = tk.StringVar()
    tk.Entry(devices_frame, textvariable=app.device_name_var).grid(row=0, column=1, sticky="we", padx=5, pady=5)

    # Serial Number
    tk.Label(devices_frame, text="Serial:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
    app.serial_var = tk.StringVar()
    tk.Entry(devices_frame, textvariable=app.serial_var).grid(row=1, column=1, sticky="we", padx=5, pady=5)

    # Model
    tk.Label(devices_frame, text="Modelo:").grid(row=2, column=0, sticky="e", padx=5, pady=5)
    app.model_var = tk.StringVar()
    tk.Entry(devices_frame, textvariable=app.model_var).grid(row=2, column=1, sticky="we", padx=5, pady=5)

    # Device IP
    tk.Label(devices_frame, text="IP:").grid(row=3, column=0, sticky="e", padx=5, pady=5)
    app.device_ip  = tk.StringVar()
    tk.Entry(devices_frame, textvariable=app.device_ip).grid(row=3, column=1, sticky="we", padx=5, pady=5)

    # Port
    tk.Label(devices_frame, text="Puerto:").grid(row=4, column=0, sticky="e", padx=5, pady=5)
    app.device_port  = tk.StringVar()
    tk.Entry(devices_frame, textvariable=app.device_port).grid(row=4, column=1, sticky="we", padx=5, pady=5)

    # Button to send device
    tk.Button(
        devices_frame,
        text="Conectar Dispositivo",
        command=app._on_connect_device
    ).grid(row=5, column=0, columnspan=2, pady=10)

    tk.Button(
        devices_frame,
        text="Iniciar Dispositivo",
        command=app._on_start_device
    ).grid(row=6, column=0, columnspan=2, pady=10)

    tk.Button(
        devices_frame,
        text="Detener Dispositivo",
        command=app._on_stop_device
    ).grid(row=7, column=0, columnspan=2, pady=10)


    # Let column 1 expand properly
    devices_frame.columnconfigure(1, weight=1)
