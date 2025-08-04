import tkinter as tk
from tkinter import ttk

def build_device_tab(app, parent):
    # Global style
    style = ttk.Style()
    style.theme_use('clam')
    style.configure("TLabel", font=("Segoe UI", 10), foreground="#222")
    style.configure("TEntry", font=("Segoe UI", 10), padding=5)
    style.configure("TButton", font=("Segoe UI", 10), padding=6)
    style.configure("TCombobox", font=("Segoe UI", 10))
    style.map("TButton",
        background=[("active", "#d9d9d9"), ("pressed", "#c0c0c0")],
        foreground=[("disabled", "#999")]
    )

    app.controller.load_devices()

    # Device Info Section
    device_frame = ttk.LabelFrame(parent, text="Device Info", padding=15)
    device_frame.pack(fill="x", padx=15, pady=10)

    app.selected_device_var = tk.StringVar()
    app.device_name_var = tk.StringVar()
    app.serial_var = tk.StringVar()
    app.model_var = tk.StringVar()

    fields = [
        ("Select Device", ttk.Combobox(device_frame, textvariable=app.selected_device_var, state="readonly")),
        ("Name", ttk.Entry(device_frame, textvariable=app.device_name_var)),
        ("Serial", ttk.Entry(device_frame, textvariable=app.serial_var)),
        ("Model", ttk.Entry(device_frame, textvariable=app.model_var)),
    ]

    for i, (label, widget) in enumerate(fields):
        ttk.Label(device_frame, text=label + ":").grid(row=i, column=0, sticky="e", padx=5, pady=5)
        widget.grid(row=i, column=1, sticky="we", padx=5, pady=5)
        if label == "Select Device":
            app.device_combo = widget
            app.device_combo.bind("<<ComboboxSelected>>", app.controller.on_select_device)

    device_frame.columnconfigure(1, weight=1)

    save_btn_frame = ttk.Frame(device_frame)
    save_btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=(10, 0))
    ttk.Button(save_btn_frame, text="Save", command=app.controller.on_save_device).pack()

    # HTTP Client Section
    http_frame = tk.LabelFrame(parent, text="HTTP Client", bg="#e8f0fe", padx=10, pady=10)
    http_frame.pack(fill="x", padx=15, pady=10)

    app.device_ip = tk.StringVar()
    app.device_port = tk.StringVar()

    style.configure("Http.TLabel", background="#e8f0fe", font=("Segoe UI", 10))
    ttk.Label(http_frame, text="IP:", style="Http.TLabel").grid(row=0, column=0, sticky="e", padx=5, pady=5)
    ttk.Entry(http_frame, textvariable=app.device_ip).grid(row=0, column=1, sticky="we", padx=5, pady=5)

    ttk.Label(http_frame, text="HTTP Port:", style="Http.TLabel").grid(row=1, column=0, sticky="e", padx=5, pady=5)
    ttk.Entry(http_frame, textvariable=app.device_port).grid(row=1, column=1, sticky="we", padx=5, pady=5)

    http_frame.columnconfigure(1, weight=1)

    style.configure("Http.TButton", background="#4285f4", foreground="black")
    http_btn_frame = ttk.Frame(http_frame)
    http_btn_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0))
    ttk.Button(http_btn_frame, text="Connect", command=app.controller.on_connect_http, style="Http.TButton").pack()

    # Modbus Serial Section
    modbus_serial_frame = ttk.LabelFrame(parent, text="Modbus Serial (RS-485)", padding=15)
    modbus_serial_frame.pack(fill="x", padx=15, pady=5)

    app.serial_port_var = tk.StringVar()
    app.baudrate_var = tk.IntVar(value=9600)
    app.slave_id_var = tk.IntVar(value=1)

    ttk.Label(modbus_serial_frame, text="Serial Port:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
    ttk.Entry(modbus_serial_frame, textvariable=app.serial_port_var).grid(row=0, column=1, sticky="we", padx=5, pady=5)

    ttk.Label(modbus_serial_frame, text="Baudrate:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
    ttk.Entry(modbus_serial_frame, textvariable=app.baudrate_var).grid(row=1, column=1, sticky="we", padx=5, pady=5)

    ttk.Label(modbus_serial_frame, text="Slave ID:").grid(row=2, column=0, sticky="e", padx=5, pady=5)
    ttk.Entry(modbus_serial_frame, textvariable=app.slave_id_var).grid(row=2, column=1, sticky="we", padx=5, pady=5)

    modbus_serial_frame.columnconfigure(1, weight=1)

    serial_btn_frame = ttk.Frame(modbus_serial_frame)
    serial_btn_frame.grid(row=3, column=0, columnspan=2, pady=(10, 0))

    for text, command in [
        ("Connect", app.controller.on_connect_modbus_serial),
        ("Start", app.controller.on_start_modbus_serial),
        ("Stop", app.controller.on_stop_modbus_serial),
        ("Reset", app.controller.on_reset_modbus_serial),
        ("Custom", app.controller.on_custom_modbus_serial),
    ]:
        ttk.Button(serial_btn_frame, text=text, command=command).pack(side="left", padx=5)

    # Modbus TCP Section
    modbus_tcp_frame = ttk.LabelFrame(parent, text="Modbus TCP", padding=15)
    modbus_tcp_frame.pack(fill="x", padx=15, pady=5)

    app.tcp_ip_var = tk.StringVar()
    app.tcp_port_var = tk.IntVar(value=502)

    ttk.Label(modbus_tcp_frame, text="IP:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
    ttk.Entry(modbus_tcp_frame, textvariable=app.tcp_ip_var).grid(row=0, column=1, sticky="we", padx=5, pady=5)

    ttk.Label(modbus_tcp_frame, text="TCP Port:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
    ttk.Entry(modbus_tcp_frame, textvariable=app.tcp_port_var).grid(row=1, column=1, sticky="we", padx=5, pady=5)

    modbus_tcp_frame.columnconfigure(1, weight=1)

    tcp_btn_frame = ttk.Frame(modbus_tcp_frame)
    tcp_btn_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0))

    for text, command in [
        ("Connect", app.controller.on_connect_modbus_tcp),
        ("Start", app.controller.on_start_modbus_tcp),
        ("Stop", app.controller.on_stop_modbus_tcp),
        ("Reset", app.controller.on_reset_modbus_tcp),
        ("Custom", app.controller.on_custom_modbus_tcp),
    ]:
        ttk.Button(tcp_btn_frame, text=text, command=command).pack(side="left", padx=5)

    # Fill combobox with devices
    app.controller.refresh_device_list()
