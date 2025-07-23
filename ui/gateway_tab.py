# ui/gateway_tab.py
import tkinter as tk
from tkinter import messagebox

def build_gateway_tab(app, parent):
    frm = tk.Frame(parent)
    frm.pack(fill="x", padx=10, pady=5)

    gw_frame = tk.LabelFrame(parent, text="Register Gateway", padx=10, pady=5)
    gw_frame.pack(fill="x", padx=10, pady=5)

    app.gw_name_var = tk.StringVar(value=app.gateway_cfg.get("name", ""))
    tk.Label(gw_frame, text="Name:").grid(row=0, column=0, sticky="e")
    tk.Entry(gw_frame, textvariable=app.gw_name_var).grid(row=0, column=1, sticky="we")

    app.org_var = tk.StringVar(value=app.gateway_cfg.get("organizationId", ""))
    tk.Label(gw_frame, text="Organization ID:").grid(row=1, column=0, sticky="e")
    tk.Entry(gw_frame, textvariable=app.org_var).grid(row=1, column=1, sticky="we")

    app.loc_var = tk.StringVar(value=app.gateway_cfg.get("location", ""))
    tk.Label(gw_frame, text="Location:").grid(row=2, column=0, sticky="e")
    tk.Entry(gw_frame, textvariable=app.loc_var).grid(row=2, column=1, sticky="we")

    tk.Button(
        gw_frame, text="Register Gateway", command=app._on_send_gateway
    ).grid(row=3, column=0, columnspan=2, pady=5)
    gw_frame.columnconfigure(1, weight=1)
