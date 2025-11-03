import os, sys

from .controllers.gateway_controller import GatewayController
from .controllers.device_controller import DeviceController
from .controllers.mqtt_controller import MqttController
from .controllers.connectivity_controller import ConnectivityController
from .services.device.device_service import DeviceService
from infrastructure.config.loader import get_gateway, save_gateway

class AppController:
    """Main application controller that coordinates UI, MQTT, and devices."""

    def __init__(self, window):
        self.window = window
        self.log = window._log

        # --- Gateway ---
        self.gateway_ctrl = GatewayController(self.log)
        self.gateway_cfg = self.gateway_ctrl.config

        # Poblar UI
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
            self.gateway_cfg, self.log, self.window.update_connectivity_status
        )
        self.connectivity.start()

        # --- Devices ---
        self.device_ctrl = DeviceController(self.mqtt_handler, self.gateway_cfg, self.log)

        self.mqtt_ctrl.connect()

    # ----------------------
    # Callbacks
    # ----------------------

    def _refresh_gateway_fields(self, gateway):
        """
        Called by GatewayManager when gateway data changes.
        Updates UI fields and internal config.
        """
        self.log(f"🌐 Gateway updated: {gateway.get('name', 'unknown')}")
        self.gateway_cfg.update(gateway)
        if self.window:
            self.window.org_id_var.set(gateway.get("organizationId", ""))
            self.window.gw_id_var.set(gateway.get("_id", ""))


    # ---------------------------
    # Device Refresh Callback
    # ---------------------------
    # def refresh_device_list(self, devices=None):
    #     """
    #     Called by DeviceManager when devices list changes.
    #     Rebuilds DeviceService instances and updates UI.
    #     """
    #     if not devices:
    #         devices = []

    #     # Detener servicios anteriores
    #     for ds in getattr(self, "devices", {}).values():
    #         ds.stop()

    #     device_services = {}
    #     for dev in devices:
    #         try:
    #             ds = DeviceService(
    #                 mqtt_handler=self.mqtt_handler,
    #                 gateway_cfg=self.gateway_cfg,
    #                 device=dev,
    #                 log=self.log,
    #                 update_fields=None  # Opcional, ya no se usa
    #             )
    #             device_services[ds.serial] = ds
    #         except Exception as e:
    #             self.log(f"❌ Error creando DeviceService para {dev.get('name')}: {e}")

    #     self.devices = device_services
    #     self.services = list(self.devices.values())

    #     if self.window:
    #         self.window.update_device_list(self.services)
    #     self.log(f"📡 Devices loaded: {len(self.devices)}")

    def _update_and_save_networks(self, networks):
        """Actualiza las redes en la config, UI, monitor y guarda el archivo."""
        current_config = get_gateway()
        current_config["known_networks"] = networks
        save_gateway(current_config)

        self.gateway_cfg = current_config
        self.window.update_known_networks_list(networks)
        
        # Actualizar el monitor de conectividad con las nuevas redes en tiempo real
        self.connectivity_monitor.known_networks = networks
        self.log("ℹ️ Lista de redes Wi-Fi actualizada.")

    def refresh_device_list(self, devices=None):
        if not devices:
            self.log("⚠️ Lista de dispositivos vacía.")
            return

        self.device_ctrl.create_all(devices)
        self.window.update_device_list(list(self.device_ctrl.devices.values()))
        self.log(f"{len(devices)} dispositivos inicializados.")


    def on_save_gateway_config(self):
        org_id = self.window.org_id_var.get()
        gw_id = self.window.gw_id_var.get()
        try:
            self.gateway_ctrl.save(org_id, gw_id)
            self.log("✅ Configuración de gateway guardada. Reiniciando...")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            self.log(f"❌ Error al guardar la configuración: {e}")


    def on_add_network(self, ssid, password):
        networks = self.gateway_cfg.get("known_networks", {})
        if ssid in networks:
            self.log(f"⚠️ La red '{ssid}' ya existe. Use 'Editar' para modificarla.")
            return
        networks[ssid] = password
        self._update_and_save_networks(networks)

    def on_edit_network(self, old_ssid, new_ssid, new_password):
        networks = self.gateway_cfg.get("known_networks", {})
        if old_ssid != new_ssid and new_ssid in networks:
            self.log(f"⚠️ Ya existe una red con el nombre '{new_ssid}'.")
            return
        if old_ssid in networks:
            del networks[old_ssid]
        networks[new_ssid] = new_password
        self._update_and_save_networks(networks)

    def on_remove_network(self, ssid):
        networks = self.gateway_cfg.get("known_networks", {})
        if ssid in networks:
            del networks[ssid]
            self._update_and_save_networks(networks)

    def on_initial_load(self):
        """Load gateway and devices after MQTT connects."""
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
