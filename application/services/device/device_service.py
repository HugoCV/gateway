# device_service.py
from threading import RLock
from typing import Dict, Any
from .connection_manager import ConnectionManager
from .commands import DeviceCommands
from .config_manager import ConfigManager


class DeviceService:
    def __init__(self, *, mqtt_handler, gateway_cfg, device, log, update_fields):
        self.mqtt = mqtt_handler
        self.gateway_cfg = gateway_cfg
        self.device = device or {}
        self.log = log
        self.update_fields = update_fields
        self._lock = RLock()
        self.commands = DeviceCommands(log)
        self._ALLOWED_CC_KEYS = {"host", "httpPort", "tcpPort", "serialPort", "baudrate", "slaveId", "logoIp", "logoPort", "mode"}
        self.cc = self.device.get("connectionConfig") or {}
        self.serial = self.device.get("serialNumber", "")
        self.name = self.device.get("name", "desconocido")
        # Create connections
        self.conns = ConnectionManager(self, log, self._send_signal)
        self.conns.create_connections(self.cc, self.device.get("modbusConfig", {}))
        self.connected = False
        self.connected_logo = False
        self.start()

    # ---------------------------
    # Lifecycle
    # ---------------------------
    def start(self):
        """Start connections based on config."""
        if self.cc.get("logoIp"):
            self.conns.logo.start()
        reader = self.cc.get("defaultReader")
        try:
            if reader == "serial" and self.conns.serial:
                self.conns.serial.start()
            elif reader == "tcp" and self.conns.tcp:
                self.conns.tcp.start()
        except Exception as e:
            self.log(f"⚠️ Error starting {reader}: {e}")
        self.update_connected()

    def stop(self):
        self.conns.stop_all()

    def update_connected(self):
        self.log("Device Updated")
        prev_tcp = self.connected
        prev_logo = self.connected_logo
        self.connected = any([
            self.conns.tcp and self.conns.tcp.is_connected(),
            self.conns.serial and self.conns.serial.is_connected(),
        ])
        self.connected_logo = bool(self.conns.logo and self.conns.logo.is_connected())
        if prev_tcp != self.connected or prev_logo != self.connected_logo:
            status = "online" if self.connected else "offline"
            logo_status = "online" if self.connected_logo else "offline"
            self.mqtt.on_change_device_connection(self.serial, status, logo_status)
    
    def update_connection_config(self, new_cfg):
        """
        Actualiza la configuración de conexión (connectionConfig) del dispositivo.
        Si cambia el modo (local/remote), ejecuta el comando correspondiente.
        """
        if not isinstance(new_cfg, dict):
            self.log("⚠️ update_connection_config: configuración inválida (se esperaba dict).")
            return False

        self.log(f"🔧 Actualizando connectionConfig: {new_cfg}")

        old_mode = self.cc.get("mode")
        new_mode = new_cfg.get("mode")

        self.cc.update(new_cfg)

        if new_mode and new_mode != old_mode:
            self.log(f"♻️ Modo cambiado de '{old_mode}' → '{new_mode}'")

            if new_mode == "local":
                self.set_local()
            elif new_mode == "remote":
                self.set_remote()
            else:
                self.log(f"⚠️ Modo desconocido: {new_mode}")
        else:
            self.log("ℹ️ No hay cambio en el modo de conexión.")

        return True


        

    # ---------------------------
    # Internal helpers
    # ---------------------------
    def _ids(self):
        org_id = self.gateway_cfg.get("organization_id") or self.gateway_cfg.get("organizationId")
        gw_id  = self.gateway_cfg.get("gateway_id") or self.gateway_cfg.get("gatewayId")
        return org_id, gw_id

    def _send_signal(self, results: Dict[str, Any], group: str) -> None:
        """Publish via MQTT with the device's serial number."""
        try:
            if not isinstance(results, dict) or not results:
                self.log("Empty result; MQTT will not be sent.")
                return
            org_id, gw_id = self._ids()
            if not org_id or not gw_id:
                self.log(f"Missing IDs in gateway_cfg: org={org_id} gw={gw_id}")
                return
            topic_info = {
                "serial_number":  self.serial,
                "organization_id": org_id,
                "gateway_id":      gw_id,
            }
            payload = {"group": group, "payload": results}
            self.mqtt.send_signal(topic_info, payload)
        except Exception as e:
            self.log(f"DeviceService._send_signal error ({self.serial}): {e}")

    # ---------------------------
    # Commands
    # ---------------------------

    def turn_on(self):
        return self.commands.turn_on(self.cc, self.conns)

    def turn_off(self):
        return self.commands.turn_off(self.cc, self.conns)

    def restart(self):
        return self.commands.restart(self.cc, self.conns)

    def set_local(self):
        return self.commands.set_local(self.conns)

    def set_remote(self):
        return self.commands.set_remote(self.conns)
