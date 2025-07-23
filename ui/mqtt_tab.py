# ui/devices_tab.py
import tkinter as tk

from mqtt.mqtt_gateway import MQTT_HOST, MQTT_PORT

def build_mqtt_tab(app, parent):
    """
    Build the mqtt configuration tab.
    `app` is the main App instance so we can access its methods and variables.
    `parent` is the tab frame inside the notebook.
    """

    # === Top bar: Broker and Port ===
    mqtt_frame = tk.LabelFrame(parent, text="Conexion", padx=10, pady=10)
    mqtt_frame.pack(fill="x", padx=10, pady=10)

    tk.Label(mqtt_frame, text="Broker:").grid(row=0, column=0, sticky="e")
    app.broker_var = tk.StringVar(value=app.gateway_cfg.get("broker", MQTT_HOST))
    tk.Entry(mqtt_frame, textvariable=app.broker_var).grid(row=0, column=1, sticky="we")

    tk.Label(mqtt_frame, text="Port:").grid(row=0, column=2, sticky="e")
    app.port_var = tk.IntVar(value=app.gateway_cfg.get("port", MQTT_PORT))
    tk.Entry(mqtt_frame, textvariable=app.port_var, width=6).grid(row=0, column=3)

    tk.Button(mqtt_frame, text="Connect", command=app._on_mqtt_connect).grid(row=0, column=4, padx=5)
    mqtt_frame.columnconfigure(1, weight=1)

    # Let column 1 expand properly
    mqtt_frame.columnconfigure(1, weight=1)
