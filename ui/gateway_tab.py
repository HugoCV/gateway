# ui/gateway_tab.py
import tkinter as tk
from tkinter import messagebox
from mqtt.mqtt_client import MQTT_HOST, MQTT_PORT

def build_gateway_tab(app, parent):

    mqtt_frame = tk.LabelFrame(parent, text="Conexion", padx=10, pady=10)
    mqtt_frame.pack(fill="x", padx=10, pady=10)

    tk.Label(mqtt_frame, text="Broker:").grid(row=0, column=0, sticky="e")
    app.broker_var = tk.StringVar(value=app.gateway_cfg.get("broker", MQTT_HOST))
    tk.Entry(mqtt_frame, textvariable=app.broker_var).grid(row=0, column=1, sticky="we")

    tk.Label(mqtt_frame, text="Puerto:").grid(row=0, column=2, sticky="e")
    app.port_var = tk.IntVar(value=app.gateway_cfg.get("port", MQTT_PORT))
    tk.Entry(mqtt_frame, textvariable=app.port_var, width=6).grid(row=0, column=3)

    tk.Button(mqtt_frame, text="Conectar", command=app._on_mqtt_connect).grid(row=0, column=4, padx=5)
    mqtt_frame.columnconfigure(1, weight=1)

    # Let column 1 expand properly
    mqtt_frame.columnconfigure(1, weight=1)

    frm = tk.Frame(parent)
    frm.pack(fill="x", padx=10, pady=5)

    gw_frame = tk.LabelFrame(parent, text="Registrar", padx=10, pady=5)
    gw_frame.pack(fill="x", padx=10, pady=5)

    app.gw_name_var = tk.StringVar(value=app.gateway_cfg.get("name", ""))
    tk.Label(gw_frame, text="Nombre:").grid(row=0, column=0, sticky="e")
    tk.Entry(gw_frame, textvariable=app.gw_name_var).grid(row=0, column=1, sticky="we")

    app.org_var = tk.StringVar(value=app.gateway_cfg.get("organizationId", ""))
    tk.Label(gw_frame, text="Organizacion ID:").grid(row=1, column=0, sticky="e")
    tk.Entry(gw_frame, textvariable=app.org_var).grid(row=1, column=1, sticky="we")

    app.loc_var = tk.StringVar(value=app.gateway_cfg.get("location", ""))
    tk.Label(gw_frame, text="Ubicacion:").grid(row=2, column=0, sticky="e")
    tk.Entry(gw_frame, textvariable=app.loc_var).grid(row=2, column=1, sticky="we")

    tk.Button(
        gw_frame, text="Registrar", command=app._on_send_gateway
    ).grid(row=3, column=0, columnspan=2, pady=5)
    gw_frame.columnconfigure(1, weight=1)
