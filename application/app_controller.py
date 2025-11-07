import os, sys

from .controllers.gateway_controller import GatewayController
from .controllers.device_controller import DeviceController
from .controllers.mqtt_controller import MqttController
from .controllers.connectivity_controller import ConnectivityController

class AppController:
    """Main application controller that coordinates UI, MQTT, and devices."""

    def __init__(self, window=None):
        self.window = window

        # Logging function (UI log or console fallback)
        if window is not None and hasattr(window, "_log"):
            self.log = window._log
        else:
            self.log = print  # fallback logger for headless mode

        # --- Gateway ---
        self.gateway_ctrl = GatewayController(self.log)
        self.gateway_cfg = self.gateway_ctrl.config

        # Populate UI only if window exists
        if self.window is not None:
            self.window.org_id_var.set(self.gateway_cfg.get("organizationId", ""))
            self.window.gw_id_var.set(self.gateway_cfg.get("gatewayId", ""))
            self.window.update_known_networks_list(self.gateway_cfg.get("known_networks", {}))

        # --- MQTT ---
        self.mqtt_ctrl = MqttController(
            self.gateway_cfg,
            self.log,
            self.on_initial_load,
            self.on_receive_command,
            self.on_receive_gateway_command
        )
        self.mqtt_handler = self.mqtt_ctrl.mqtt

        # --- Connectivity ---
        self.connectivity = ConnectivityController(
            self.gateway_cfg,
            self.log,
            self.window.update_connectivity_status if self.window else None
        )
        self.connectivity.start()

        # --- Devices ---
        self.device_ctrl = DeviceController(self.mqtt_handler, self.gateway_cfg, self.log)

        self.mqtt_ctrl.connect()

    # ----------------------
    # Callbacks
    # ----------------------

    def _refresh_gateway_fields(self, gateway):
        self.log(f"🌐 Gateway updated: {gateway.get('name', 'unknown')}")
        self.gateway_cfg.update(gateway)

        if self.window:
            self.window.org_id_var.set(gateway.get("organizationId", ""))
            self.window.gw_id_var.set(gateway.get("_id", ""))

    def refresh_device_list(self, devices=None):
        if not devices:
            self.log("⚠️ Lista de dispositivos vacía.")
            return

        self.device_ctrl.create_all(devices)

        if self.window:
            self.window.update_device_list(list(self.device_ctrl.devices.values()))

        self.log(f"{len(devices)} dispositivos inicializados.")

    def on_save_gateway_config(self):
        if not self.window:
            self.log("⚠️ Cannot save gateway config without UI.")
            return

        org_id = self.window.org_id_var.get()
        gw_id = self.window.gw_id_var.get()
        try:
            self.gateway_ctrl.save(org_id, gw_id)
            self.log("✅ Configuración de gateway guardada. Reiniciando...")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            self.log(f"❌ Error al guardar la configuración: {e}")

    def on_initial_load(self):
        self.log("📥 Loading gateway and devices...")
        from application.managers.gateway_manager import GatewayManager
        from application.managers.device_manager import DeviceManager

        self.gateway_manager = GatewayManager(self.mqtt_handler, self._refresh_gateway_fields, self.log)
        self.device_manager = DeviceManager(self.mqtt_handler, self.refresh_device_list, self.log)

        self.gateway_manager.load_gateway()
        self.device_manager.load_devices()

    def on_receive_command(self, device_serial, command):
        self.device_ctrl.handle_command(device_serial, command)

    def on_receive_gateway_command(self, command):
        if command.get("action") == "restart":
            os.execv(sys.executable, [sys.executable] + sys.argv)
