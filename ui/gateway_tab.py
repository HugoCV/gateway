import tkinter as tk
from tkinter import ttk
from infrastructure.mqtt.mqtt_client import MQTT_HOST, MQTT_PORT

def build_gateway_tab(app, parent):
    # === Estilo visual ===
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

    # === MQTT Frame ===
    mqtt_frame = ttk.LabelFrame(parent, text="Conexión MQTT", padding=15)
    mqtt_frame.pack(fill="x", padx=15, pady=(15, 10))

    app.mqtt_host = tk.StringVar(value=app.controller.gateway_cfg.get("broker", MQTT_HOST))
    app.port_var = tk.IntVar(value=app.controller.gateway_cfg.get("port", MQTT_PORT))

    ttk.Label(mqtt_frame, text="Broker:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
    ttk.Entry(mqtt_frame, textvariable=app.mqtt_host).grid(row=0, column=1, sticky="we", padx=5, pady=5)

    ttk.Label(mqtt_frame, text="Puerto:").grid(row=0, column=2, sticky="e", padx=5, pady=5)
    ttk.Entry(mqtt_frame, textvariable=app.port_var, width=6).grid(row=0, column=3, padx=5, pady=5)

    # ttk.Button(mqtt_frame, text="Conectar", command=app.controller.on_connect_mqtt).grid(row=0, column=4, padx=10)

    mqtt_frame.columnconfigure(1, weight=1)

    # === Registro de Gateway ===
    gw_frame = ttk.LabelFrame(parent, text="Puerta de enlace", padding=15)
    gw_frame.pack(fill="x", padx=15, pady=(5, 10))

    app.gw_name_var = tk.StringVar(value=app.controller.gateway_cfg.get("name", ""))
    app.org_var = tk.StringVar(value=app.controller.gateway_cfg.get("organizationId", ""))
    app.loc_var = tk.StringVar(value=app.controller.gateway_cfg.get("location", ""))

    fields = [
        ("Nombre", app.gw_name_var),
        ("Organización ID", app.org_var),
        ("Ubicación", app.loc_var)
    ]

    for i, (label, var) in enumerate(fields):
        ttk.Label(gw_frame, text=label + ":").grid(row=i, column=0, sticky="e", padx=5, pady=5)
        ttk.Entry(gw_frame, textvariable=var).grid(row=i, column=1, sticky="we", padx=5, pady=5)

    # ttk.Button(gw_frame, text="Cargar datos", command=app.controller.on_initial_load).grid(
    #     row=len(fields), column=0, columnspan=2, pady=10
    # )

    gw_frame.columnconfigure(1, weight=1)
