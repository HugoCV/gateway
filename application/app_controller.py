import os, sys, time, json
import threading
from application.managers.gateway_manager import GatewayManager
from application.managers.device_manager import DeviceManager
from application.services.device_service import DeviceService
from infrastructure.connectivity.connectivity import ConnectivityMonitor
from infrastructure.mqtt.mqtt_client import MqttClient
from infrastructure.config.loader import get_gateway, save_gateway

# =========================
# Global
# =========================


class AppController:
    """
    Controlador principal de la aplicación Tkinter.
    Gestiona conexiones MQTT, Modbus (TCP/Serial), Logo y HTTP.
    """

    def __init__(self, window):
        self.window = window
        self.log = window._log
        self.gateway_cfg = get_gateway()
        self.mqtt_handler = MqttClient(
            self.gateway_cfg,
            self.on_initial_load,
            log_callback=self.window._log,
            command_callback=self.on_receive_command,
            command_gateway_callback=self.on_receive_gateway_command
        )
        
        # Poblar campos de la UI con la configuración actual
        self.window.org_id_var.set(self.gateway_cfg.get("organizationId", ""))
        self.window.gw_id_var.set(self.gateway_cfg.get("gatewayId", ""))

        self.connectivity_monitor = ConnectivityMonitor(
                log_callback=self.window._log,
                known_networks=self.gateway_cfg.get("known_networks", {})
            )
        self.connectivity_monitor.start()

        # Conectar MQTT al final
        self.on_connect_mqtt()

        self.device_manager = DeviceManager(self.mqtt_handler, self.refresh_device_list, self.window._log)
        self.gateway_manager = GatewayManager(self.mqtt_handler, self._refresh_gateway_fields, self.window._log)
        self.devices = {}
        
    # === commands ===
    def on_receive_gateway_command(self, command):
        print("on_receive_gateway_command", command)
        
        match command["action"]:
            case "restart":
                os.execv(sys.executable, [sys.executable] + sys.argv)
            case "restart-gateway":
                print("restart")

    
    def on_receive_command(self, device_serial, command):
        if not self.devices:
            self.window._log(f"no hay dispositivos conectados commando recivido {command}")
        if not (ds := self.devices.get(device_serial)):
                    self.window._log("⚠️ No device selected.")
                    return    
        match command["action"]:
            case "update-connections":
                    ds.update_connection_config(command["params"])
            case "update-status":
                value = str(command.get("params", {}).get("value", "")).lower()
                if value == "on":
                    self.log(f"El dispositivo {ds.name} se mandó a encender")
                    ds.turn_on()
                elif value == "off":
                    self.log(f"El dispositivo {ds.name} se mandó a apagar")
                    ds.turn_off()
                elif value == "restart":
                    self.log(f"El dispositivo {ds.name} se mandó a reiniciar")
                    ds.restart()
            case "update-config":
                print("update-config", command["params"]["value"], "device_serial", device_serial)
        
    # === initial load ===
    def on_initial_load(self):
        self.gateway_manager.load_gateway()
        self.device_manager.load_devices()

    # === Gateway ===
    # NOTE: This method is currently unused as the UI fields have been removed.
    def _refresh_gateway_fields(self, gateway):
        print("refresh_gateway_fields", gateway)

    def on_save_gateway_config(self):
        org_id = self.window.org_id_var.get()
        gw_id = self.window.gw_id_var.get()

        new_config = {
            "organizationId": org_id,
            "gatewayId": gw_id
        }

        try:
            save_gateway(new_config)
            self.log("✅ Configuración de gateway guardada. Reiniciando...")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            self.log(f"❌ Error al guardar la configuración: {e}")
    
    # === MQTT ===
    def on_connect_mqtt(self):
        self.mqtt_handler.connect()

    # === Devices ===
    def get_device_by_name(self, name):
        return next((d for d in self.device_manager.devices if d.get("name") == name), None)

    def refresh_device_list(self, devices=None) -> None:
        if devices is None:
            devices = {}

        self.devices = self.create_all_devices(devices)
        self.services = list(self.devices.values())
        if self.window:
            self.window.update_device_list(self.services)

    def create_all_devices(self, devices):
        for ds in getattr(self, "devices", {}).values():
            ds.stop()

        device_services = {}
        for dev in devices:
            ds = DeviceService(
                mqtt_handler=self.mqtt_handler,
                gateway_cfg=self.gateway_cfg,
                device=dev,
                log=self.window._log,
                update_fields=None # self.update_device_fields -> No longer used
            )

            device_services[ds.serial] = ds
        return device_services
