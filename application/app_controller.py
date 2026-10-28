import os
import sys
from threading import Event
from typing import Callable, Optional

from application.managers.gateway_manager import GatewayManager
from application.managers.device_manager import DeviceManager
from application.services.device_service import DeviceService
from application.services.gateway_command_service import GatewayCommandService
from application.services.device_command_service import DeviceCommandService
from infrastructure.connectivity.connectivity import ConnectivityMonitor
from infrastructure.mqtt.mqtt_client import MqttClient
from infrastructure.config.loader import get_gateway, save_gateway, GATEWAY_PATH
from infrastructure.activity_log import log_value

# =========================
# Global
# =========================


class AppController:
    """
    Main controller for the Tkinter app.
    Manages MQTT, Modbus TCP/RTU, and HTTP connections.
    """

    def __init__(
        self,
        window=None,
        log_callback: Optional[Callable[[str], None]] = None,
        status_callback: Optional[Callable[[bool, str], None]] = None,
        restart_callback: Optional[Callable[[], None]] = None,
    ):
        self.window = window
        self.log = log_callback or getattr(window, "_log", print)
        self._closed = False
        self.restart_callback = restart_callback
        self.gateway_cfg = get_gateway()
        organization_id = self.gateway_cfg.get("organizationId") or self.gateway_cfg.get("organization_id")
        gateway_id = self.gateway_cfg.get("gatewayId") or self.gateway_cfg.get("gateway_id")
        self.log(
            f"Identidad del Gateway: archivo={log_value(os.path.abspath(GATEWAY_PATH))}; "
            f"organizationId={'presente' if organization_id else 'ausente'}; "
            f"gatewayId={'presente' if gateway_id else 'ausente'}."
        )
        self.gateway_commands = GatewayCommandService(
            os.path.join(os.path.dirname(GATEWAY_PATH), "gateway-commands.json"),
            organization_id, gateway_id, self.request_restart,
            lambda result: self.mqtt_handler.publish_gateway_command_result(result), self.log,
        )
        self.device_commands = DeviceCommandService(
            os.path.join(os.path.dirname(GATEWAY_PATH), "device-commands.json"),
            organization_id, gateway_id, self._execute_device_command,
            lambda **result: self.mqtt_handler.publish_device_command_result(**result), self.log,
        )
        self.mqtt_handler = MqttClient(
            self.gateway_cfg,
            self.on_initial_load,
            log_callback=self.log,
            command_callback=self.on_receive_command,
            command_gateway_callback=self.on_receive_gateway_command,
            gateway_results_callback=self.flush_command_results,
            device_config_reload_callback=self.on_device_config_reload,
        )

        if self.window:
            self.window.org_id_var.set(self.gateway_cfg.get("organizationId", ""))
            self.window.gw_id_var.set(self.gateway_cfg.get("gatewayId", ""))

        self.connectivity_monitor = ConnectivityMonitor(
            log_callback=self.log,
            status_callback=(
                status_callback or (self.window.update_connectivity_status if self.window else None)
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
        self.log(f"Comando del Gateway recibido: {log_value(command.get('action'))}.")

        self.gateway_commands.receive(command)

    
    def flush_command_results(self):
        self.gateway_commands.flush_results()
        self.device_commands.flush_results()

    def on_receive_command(self, device_serial, command):
        self.device_commands.receive(device_serial, command)

    def _execute_device_command(self, device_serial, command):
        action = command.get("action")
        command_id = command.get("commandId")

        if not (ds := self.devices.get(device_serial)):
            self.log(
                f"⚠️ No se encontró el dispositivo {device_serial} "
                f"para ejecutar {log_value(action)}"
            )
            return {"status": "failed", "reason": "device_not_found"}

        if action == "update-connections":
            try:
                ds.update_connections(command.get("params", {}).get("connections"))
            except Exception as error:
                self.log(f"❌ Error aplicando conexión a {device_serial}: {type(error).__name__}.")
                raise
        elif action == "device-command":
            params = command.get("params", {})
            channel_id = params.get("channelId")
            item_id = params.get("itemId")
            action_id = params.get("actionId")
            succeeded = False
            reason = None

            try:
                self.log(
                    f"Ejecutando {item_id}.{action_id} "
                    f"en canal {channel_id} para {ds.name}"
                )
                succeeded, reason = ds.execute_action(
                    channel_id, item_id, action_id
                )
                if not succeeded and not reason:
                    reason = "device_write_failed"
            except Exception as error:
                reason = "command_exception"
                self.log(
                    f"❌ Error ejecutando acción {item_id}.{action_id} "
                    f"en {device_serial}: {error}"
                )

            self.log(
                f"Resultado de {log_value(item_id)}.{log_value(action_id)} en {device_serial}: "
                f"{'correcto' if succeeded else 'fallido'}; motivo={log_value(reason)}."
            )
            return {"status": "success" if succeeded else "failed", "reason": reason}
        elif action == "update-config":
            self.log(f"⚠️ update-config recibido para {device_serial}; su aplicación no está implementada.")
        
    # === initial load ===
    def on_initial_load(self):
        self.gateway_manager.load_gateway()
        self.device_manager.load_devices()

    def on_device_config_reload(self):
        self.device_manager.load_devices()

    # === Gateway ===
    # NOTE: This method is currently unused as the UI fields have been removed.
    def _refresh_gateway_fields(self, gateway):
        return

    def runtime_snapshot(self):
        """Expose only the identity and device fields needed by local windows."""
        devices = []
        for device in list(self.devices.values()):
            channel_names = {
                channel.get("id"): channel.get("name")
                for channel in device.profile.get("channels", [])
                if isinstance(channel, dict) and channel.get("id")
            }
            devices.append({
                "name": device.name,
                "serial": device.serial,
                "channels": [
                    {
                        "id": channel_id,
                        "name": channel_names.get(channel_id) or channel_id,
                        "connected": device.channel_status.get(channel_id),
                    }
                    for channel_id in device.channels
                ],
                "connected": bool(device.connected),
            })
        signal_publications = []
        snapshot_signals = getattr(getattr(self, "mqtt_handler", None),
                                   "sent_signals_snapshot", None)
        if callable(snapshot_signals):
            for publication in snapshot_signals():
                device = self.devices.get(publication["serial"])
                if not device or publication["channelId"] not in device.channels:
                    continue
                channel = next((entry for entry in device.profile.get("channels", [])
                                if isinstance(entry, dict)
                                and entry.get("id") == publication["channelId"]), None)
                if channel is None:
                    continue
                definitions = {
                    str(item["id"]): item
                    for item in channel.get("items", [])
                    if isinstance(item, dict) and item.get("id")
                }
                signals = []
                for item_id, data in publication["payload"].items():
                    definition = definitions.get(item_id, {})
                    read = definition.get("read") or {}
                    if not isinstance(read, dict):
                        read = {}
                    signals.append({
                        "id": item_id,
                        "name": definition.get("name") or item_id,
                        "address": read.get("address"),
                        "value": data.get("value") if isinstance(data, dict) else data,
                    })
                signal_publications.append({
                    "deviceName": device.name,
                    "serial": device.serial,
                    "channelName": channel.get("name") or publication["channelId"],
                    "channelId": publication["channelId"],
                    "topic": publication["topic"],
                    "sentAt": publication["sentAt"],
                    "delivery": publication["delivery"],
                    "omitted": publication["omitted"],
                    "signals": signals,
                })
        return {
            "gateway": {key: self.gateway_cfg.get(key, "")
                        for key in ("organizationId", "gatewayId")},
            "devices": devices,
            "signalPublications": signal_publications,
        }

    def save_gateway_identity(self, organization_id, gateway_id):
        # Environment values take precedence in get_gateway(); avoid reporting
        # success for an edit that would be silently undone on restart.
        for name, value in (("GATEWAY_ORGANIZATION_ID", organization_id),
                            ("GATEWAY_ID", gateway_id)):
            if os.getenv(name) and os.getenv(name) != value:
                raise ValueError(f"{name} está fijado en .env. Edite ese archivo y reinicie el servicio.")
        current_config = get_gateway()
        current_config.update(organizationId=organization_id, gatewayId=gateway_id)
        save_gateway(current_config)
        self.log("✅ Configuración de gateway guardada. Reiniciando el servicio...")

    def request_restart(self):
        if self.restart_callback is not None:
            self.restart_callback()
        else:
            os.execv(sys.executable, [sys.executable] + sys.argv)

    def on_save_gateway_config(self):
        if self.window:
            try:
                self.save_gateway_identity(self.window.org_id_var.get(),
                                           self.window.gw_id_var.get())
                self.request_restart()
            except Exception as error:
                self.log(f"❌ Error al guardar la configuración: {error}")
    
    # === MQTT ===
    def on_connect_mqtt(self):
        self.mqtt_handler.connect()

    # === Devices ===
    def get_device_by_name(self, name):
        return next((d for d in self.device_manager.devices if d.get("name") == name), None)

    def refresh_device_list(self, devices=None) -> None:
        if devices is None:
            devices = {}

        self.mqtt_handler.clear_sent_signals()
        self.devices = self.create_all_devices(devices)
        self.services = list(self.devices.values())
        if self.window:
            self.window.update_device_list(self.services)

    def create_all_devices(self, devices):
        existing = getattr(self, "devices", {})
        device_services = {}
        for dev in devices:
            serial = dev.get("serialNumber")
            previous = existing.get(serial)
            runtime_fields = ("name", "serialNumber", "deviceProfileId", "connections", "parameters", "commissioningStatus")
            if previous and all(previous.device.get(field) == dev.get(field) for field in runtime_fields):
                device_services[serial] = previous
                continue
            if previous:
                previous.stop()
            ds = DeviceService(
                mqtt_handler=self.mqtt_handler,
                gateway_cfg=self.gateway_cfg,
                device=dev,
                log=self.log,
                update_fields=None # self.update_device_fields -> No longer used
            )

            device_services[ds.serial] = ds
        for serial, previous in existing.items():
            if serial not in device_services:
                previous.stop()
        return device_services
