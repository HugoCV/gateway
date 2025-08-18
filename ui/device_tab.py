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
              foreground=[("disabled", "#999")])

    # Configure parent grid for 2 columns
    parent.columnconfigure(0, weight=1)
    parent.columnconfigure(1, weight=1)

    # Device Info Section
    device_frame = ttk.LabelFrame(parent, text="Device Info", padding=15)
    device_frame.grid(row=0, column=0, sticky="nsew", padx=15, pady=10)

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

    # HTTP Client Section
    http_frame = ttk.LabelFrame(parent, text="HTTP Client", padding=15, style="Http.TLabel", relief="solid")
    http_frame.grid(row=0, column=1, sticky="nsew", padx=15, pady=10)

    app.http_ip_var = tk.StringVar()
    app.http_port_var = tk.StringVar()

    style.configure("Http.TLabel")
    ttk.Label(http_frame, text="HTTP IP:", style="Http.TLabel").grid(row=0, column=0, sticky="e", padx=5, pady=5)
    ttk.Entry(http_frame, textvariable=app.http_ip_var).grid(row=0, column=1, sticky="we", padx=5, pady=5)
    ttk.Label(http_frame, text="HTTP Port:", style="Http.TLabel").grid(row=1, column=0, sticky="e", padx=5, pady=5)
    ttk.Entry(http_frame, textvariable=app.http_port_var).grid(row=1, column=1, sticky="we", padx=5, pady=5)

    http_frame.columnconfigure(1, weight=1)

    http_btn_frame = ttk.Frame(http_frame)
    http_btn_frame.grid(row=3, column=0, columnspan=2, pady=(10, 5), sticky="we")
    wrap = 3

    for c in range(wrap):
        http_btn_frame.columnconfigure(c, weight=1)

    http_buttons = [
        ("Conectar", app.controller.on_connect_http),
        ("Leer Fallas", app.controller.on_http_read_fault),
    ]
    for idx, (text, cmd) in enumerate(http_buttons):
        r = idx // wrap
        c = idx % wrap
        ttk.Button(
            http_btn_frame,
            text=text,
            command=cmd
        ).grid(row=r, column=c, padx=5, pady=5, sticky="we")


    # Modbus Serial Section
    modbus_serial_frame = ttk.LabelFrame(parent, text="Modbus Serial (RS-485)", padding=15)
    modbus_serial_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=10)

    app.serial_port_var = tk.StringVar()
    app.baudrate_var = tk.IntVar(value=8444)
    app.slave_id_var = tk.IntVar(value=1)
    app.register_var = tk.IntVar(value=0)

    labels = ["Serial Port:", "Baudrate:", "Slave ID:"]
    vars_ = [app.serial_port_var, app.baudrate_var, app.slave_id_var]
    for i, (text, var) in enumerate(zip(labels, vars_)):
        ttk.Label(modbus_serial_frame, text=text).grid(row=i, column=0, sticky="e", padx=5, pady=5)
        ttk.Entry(modbus_serial_frame, textvariable=var).grid(row=i, column=1, sticky="we", padx=5, pady=5)

    modbus_serial_frame.columnconfigure(1, weight=1)
    serial_btn_frame = ttk.Frame(modbus_serial_frame)
    serial_btn_frame.grid(row=3, column=0, columnspan=2, pady=(10, 5), sticky="we")
    wrap = 3

    for c in range(wrap):
        serial_btn_frame.columnconfigure(c, weight=1)

    modbus_buttons = [
        ("Conectar", app.controller.on_connect_modbus_serial),
        ("Iniciar",  app.controller.on_start_modbus_serial),
        ("Apagar",   app.controller.on_stop_modbus_serial),
        ("Reiniciar",app.controller.on_reset_modbus_serial),
        ("Leer Multiple", app.controller.on_multiple_modbus_serial),
        ("Local", app.controller.on_set_remote_serial),
    ]
    for idx, (text, cmd) in enumerate(modbus_buttons):
        r = idx // wrap
        c = idx % wrap
        ttk.Button(
            serial_btn_frame,
            text=text,
            command=cmd
        ).grid(row=r, column=c, padx=5, pady=5, sticky="we")

    # Modbus TCP Section
    modbus_tcp_frame = ttk.LabelFrame(parent, text="Modbus TCP", padding=15)
    modbus_tcp_frame.grid(row=1, column=1, sticky="nsew", padx=15, pady=10)

    app.tcp_ip_var = tk.StringVar()
    app.tcp_port_var = tk.IntVar(value=502)
    ttk.Label(modbus_tcp_frame, text="TCP IP:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
    ttk.Entry(modbus_tcp_frame, textvariable=app.tcp_ip_var).grid(row=0, column=1, sticky="we", padx=5, pady=5)
    ttk.Label(modbus_tcp_frame, text="TCP Port:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
    ttk.Entry(modbus_tcp_frame, textvariable=app.tcp_port_var).grid(row=1, column=1, sticky="we", padx=5, pady=5)

    modbus_tcp_frame.columnconfigure(1, weight=1)
    tcp_btn_frame = ttk.Frame(modbus_tcp_frame)
    tcp_btn_frame.grid(row=3, column=0, columnspan=2, pady=(10, 5), sticky="we")
    wrap = 3

    for c in range(wrap):
        tcp_btn_frame.columnconfigure(c, weight=1)

    tcp_buttons = [
        ("Conectar", app.controller.on_connect_modbus_tcp),
        ("Iniciar",  app.controller.on_start_modbus_tcp),
        ("Apagar",   app.controller.on_stop_modbus_tcp),
        ("Reiniciar",app.controller.on_reset_modbus_tcp),
        ("Leer Multiple", app.controller.on_multiple_modbus_tcp),
        ("Local", app.controller.on_set_remote_tcp),
    ]
    for idx, (text, cmd) in enumerate(tcp_buttons):
        r = idx // wrap
        c = idx % wrap
        ttk.Button(
            tcp_btn_frame,
            text=text,
            command=cmd
        ).grid(row=r, column=c, padx=5, pady=5, sticky="we")

    # Logo Section
    logo_tcp_frame = ttk.LabelFrame(parent, text="Logo", padding=15)
    logo_tcp_frame.grid(row=2, column=0, sticky="nsew", padx=15, pady=10)
    # Placeholder for second column in row 2
    parent.grid_rowconfigure(2, weight=0)
    spacer = ttk.Frame(parent)
    spacer.grid(row=2, column=1, sticky="nsew")

    app.logo_ip_var = tk.StringVar()
    app.logo_port_var = tk.IntVar(value=502)
    ttk.Label(logo_tcp_frame, text="Logo IP:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
    ttk.Entry(logo_tcp_frame, textvariable=app.logo_ip_var).grid(row=0, column=1, sticky="we", padx=5, pady=5)
    ttk.Label(logo_tcp_frame, text="Logo Port:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
    ttk.Entry(logo_tcp_frame, textvariable=app.logo_port_var).grid(row=1, column=1, sticky="we", padx=5, pady=5)
    logo_tcp_frame.columnconfigure(1, weight=1)

    tcp_btn_frame = ttk.Frame(logo_tcp_frame)
    tcp_btn_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0))
    for text, command in [
        ("Connect", app.controller.on_connect_logo),
        ("Start", app.controller.on_start_logo),
        ("Stop", app.controller.on_stop_logo),
        ("Leer", app.controller.on_read_logo),
        ("Leer multiple", app.controller.on_multiple_logo)
    ]:
        ttk.Button(tcp_btn_frame, text=text, command=command).pack(side="left", padx=5)

        