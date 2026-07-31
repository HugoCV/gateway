import os
import sys
from threading import Event
from typing import Callable, Optional

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
    Main controller for the Tkinter app.
    Manages MQTT, Modbus (TCP/Serial), Logo, and HTTP connections.
    """

    def __init__(
        self,
        window=None,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        self.window = window
        self.log = log_callback or getattr(window, "_log", print)
        self._closed = False
        self.gateway_cfg = get_gateway()
        self.mqtt_handler = MqttClient(
            self.gateway_cfg,
            self.on_initial_load,
            log_callback=self.log,
            command_callback=self.on_receive_command,
            command_gateway_callback=self.on_receive_gateway_command
        )

        if self.window:
            self.window.org_id_var.set(self.gateway_cfg.get("organizationId", ""))
            self.window.gw_id_var.set(self.gateway_cfg.get("gatewayId", ""))
            self.window.update_known_networks_list(
                self.gateway_cfg.get("known_networks", {})
            )

        self.connectivity_monitor = ConnectivityMonitor(
            log_callback=self.log,
            known_networks=self.gateway_cfg.get("known_networks", {}),
            status_callback=(
                self.window.update_connectivity_status if self.window else None
            ),
        )
        self.connectivity_monitor.start()

        self.device_manager = DeviceManager(
            self.mqtt_handler,
            self.refresh_device_list,
            self.log,
        )
        self.gateway_manager = GatewayManager(
            self.mqtt_handler,
            self._refresh_gateway_fields,
            self.log,
        )
        self.devices = {}

        # Managers must exist before MQTT can invoke on_initial_load.
        self.on_connect_mqtt()

    def run(self, stop_event: Optional[Event] = None) -> None:
        """Keep the non-graphical gateway process alive until it is stopped."""
        event = stop_event or Event()
        self.log("Gateway ejecutándose en segundo plano.")
        event.wait()

    def close(self) -> None:
        """Stop device, connectivity, and MQTT workers exactly once."""
        if self._closed:
            return
        self._closed = True

        for device in list(getattr(self, "devices", {}).values()):
            try:
                device.stop()
            except Exception as error:
                self.log(f"⚠️ Error deteniendo dispositivo: {error}")

        try:
            self.connectivity_monitor.stop()
        except Exception as error:
            self.log(f"⚠️ Error deteniendo conectividad: {error}")

        try:
            self.mqtt_handler.disconnect()
        except Exception as error:
            self.log(f"⚠️ Error desconectando MQTT: {error}")
        
    # === commands ===
    def on_receive_gateway_command(self, command):
        print("on_receive_gateway_command", command)

        action = command.get("action")
        if action == "restart":
            os.execv(sys.executable, [sys.executable] + sys.argv)
        elif action == "restart-gateway":
            print("restart")

    
    def on_receive_command(self, device_serial, command):
        action = command.get("action")
        command_id = command.get("commandId")

        if not (ds := self.devices.get(device_serial)):
            self.log(
                f"⚠️ No se encontró el dispositivo {device_serial} "
                f"para ejecutar {command}"
            )
            if action == "device-command" and command_id:
                params = command.get("params", {})
                self.mqtt_handler.publish_device_command_result(
                    device_serial=device_serial,
                    command_id=command_id,
                    status="failed",
                    command_name=str(params.get("command", "")),
                    value=str(params.get("value", "on")),
                    channel=params.get("channel"),
                    reason="device_not_found",
                )
            return

        if action == "update-connections":
            ds.update_connection_config(command["params"])
        elif action == "device-command":
            params = command.get("params", {})
            value = str(params.get("command", ""))
            command_value = str(params.get("value", "on"))
            channel = params.get("channel")
            normalized_value = value.lower()
            succeeded = False
            reason = None

            try:
                if normalized_value == "turnon":
                    self.log(f"El dispositivo {ds.name} se mandó a encender")
                elif normalized_value == "turnoff":
                    self.log(f"El dispositivo {ds.name} se mandó a apagar")
                elif normalized_value == "restart":
                    self.log(f"El dispositivo {ds.name} se mandó a reiniciar")
                else:
                    self.log(
                        f"Ejecutando comando {value}.{command_value} "
                        f"en canal {channel or 'auto'} para {ds.name}"
                    )
                succeeded, reason = ds.execute_command_with_confirmation(
                    value, channel, command_value
                )
                if not succeeded and not reason:
                    reason = "device_write_failed"
            except Exception as error:
                reason = "command_exception"
                self.log(
                    f"❌ Error ejecutando comando {value} "
                    f"en {device_serial}: {error}"
                )

            if command_id:
                self.mqtt_handler.publish_device_command_result(
                    device_serial=device_serial,
                    command_id=command_id,
                    status="success" if succeeded else "failed",
                    command_name=value,
                    value=command_value,
                    channel=channel,
                    reason=reason,
                )
            else:
                self.log(
                    f"⚠️ Comando {value} sin commandId; "
                    "no se puede confirmar al backend"
                )
        elif action == "update-config":
            print("update-config", command["params"]["value"], "device_serial", device_serial)
        
    # === initial load ===
    def on_initial_load(self):
        self.gateway_manager.load_gateway()
        self.device_manager.load_devices()

    # === Gateway ===
    # NOTE: This method is currently unused as the UI fields have been removed.
    def _refresh_gateway_fields(self, gateway):
        return

    def on_save_gateway_config(self):
        if not self.window:
            self.log("⚠️ Guardar configuración requiere la interfaz gráfica.")
            return

        org_id = self.window.org_id_var.get()
        gw_id = self.window.gw_id_var.get()

        # Preserve known networks and other settings that were already saved.
        current_config = get_gateway()
        current_config["organizationId"] = org_id
        current_config["gatewayId"] = gw_id

        try:
            save_gateway(current_config)
            self.log("✅ Configuración de gateway guardada. Reiniciando...")
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            self.log(f"❌ Error al guardar la configuración: {e}")
    
    # === MQTT ===
    def on_connect_mqtt(self):
        self.mqtt_handler.connect()

    # === Known Networks Management ===
    def _update_and_save_networks(self, networks):
        """Update networks in config, UI, and monitor, then save the file."""
        current_config = get_gateway()
        current_config["known_networks"] = networks
        save_gateway(current_config)

        self.gateway_cfg = current_config
        if self.window:
            self.window.update_known_networks_list(networks)
        
        # Update the connectivity monitor with the new networks in real time.
        self.connectivity_monitor.known_networks = networks
        self.log("ℹ️ Lista de redes Wi-Fi actualizada.")

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
                log=self.log,
                update_fields=None # self.update_device_fields -> No longer used
            )

            device_services[ds.serial] = ds
        return device_services
