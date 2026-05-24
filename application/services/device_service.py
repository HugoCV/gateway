# device_service.py
import threading
from typing import Dict, Any, Optional
from threading import RLock

# from infrastructure.http.http_client import HttpClient
from infrastructure.logo.logo_client import LogoModbusClient
from infrastructure.modbus.modbus_tcp import ModbusTcp
from infrastructure.modbus.modbus_serial import ModbusSerial



# Per-key scales apply when the key exists and the value is not None.

class DeviceService:
    """
    Per-device service that manages its own connections to:
      - HTTP (HttpClient)
      - Modbus TCP (ModbusTcp)
      - Modbus Serial (ModbusSerial)
      - LOGO! (LogoModbusClient)
    and publishes readings via MQTT using the device's serial number.
    """

    def __init__(
        self,
        *,
        mqtt_handler,
        gateway_cfg: Dict[str, Any],
        device: Dict[str, Any],
        log,
        update_fields,
    ) -> None:
        self.mqtt = mqtt_handler
        self.gateway_cfg = gateway_cfg
        self.device = device or {}
        self.log = log
        self.update_fields = update_fields
        self._lock = RLock()
        # self.http_interval =0.5

        # Allowed connectionConfig keys
        self._ALLOWED_CC_KEYS = {
            "host", "httpPort", "tcpPort",
            "serialPort", "baudrate", "slaveId",
            "logoIp", "logoPort", "mode"
        }

        # Device identity
        self.device_id: str = (
            self.device.get("_id")
            or self.device.get("serialNumber")
            or self.device.get("name")
            or ""
        )
        self.name = self.device.get("name", "desconocido")
        self.model: str = self.device.get("deviceModel", "")
        self.serial: str = self.device.get("serialNumber", "")
        self.cc: Dict[str, Any] = self.device.get("connectionConfig") or {}

        # Per-device handlers
        # self.http: Optional[HttpClient] = None
        # self.modbus_tcp: Optional[ModbusTcp] = None
        # self.modbus_serial: Optional[ModbusSerial] = None
        # self.logo: Optional[LogoModbusClient] = None

        # self.base_url = f"http://{self.cc['host']}:{self.cc['httpPort']}/api/dashboard"
        # self.http = HttpClient(self, self._send_signal, self.log)
        self.modbus_serial = ModbusSerial(self, self._send_signal, self.log, self.cc["serialPort"], self.cc["baudrate"], self.cc["slaveId"])
        self.modbus_tcp = ModbusTcp(self, self._send_signal, self.log, self.cc["host"], self.cc["tcpPort"], self.cc["slaveId"])
        self.logo = LogoModbusClient(self, self.log, self._send_signal, self.cc.get("logoIp"), self.cc.get("logoPort"))
        self.connected: bool = False
        self.connected_logo = False
        self.start()

    def __del__(self):
        """Ensure cleanup on instance deletion."""
        self.stop()

    def stop(self) -> None:
        """Stop all per-device connections and threads."""
        print(f"⏹️ Stopping DeviceService for {self.device_id}")

        try:
            if self.modbus_tcp:
                self.modbus_tcp.stop()
        except Exception as e:
            self.log(f"⚠️ Error stopping Modbus TCP: {e}")

        try:
            if self.modbus_serial:
                self.modbus_serial.stop()
        except Exception as e:
            self.log(f"⚠️ Error stopping Modbus Serial: {e}")

        try:
            if self.logo:
                self.logo.stop()
        except Exception as e:
            self.log(f"⚠️ Error stopping LOGO: {e}")

        try:
            if self.http:
                self.http.stop()
        except Exception as e:
            self.log(f"⚠️ Error stopping HTTP: {e}")

    def update_connected(self) -> None:
        """Check device connection status (TCP/Serial/LOGO) and notify via MQTT if changed."""
        prev_connected = getattr(self, "connected", False)
        prev_connected_logo = getattr(self, "connected_logo", False)

        self.connected = any([
            self.modbus_tcp and self.modbus_tcp.is_connected(),
            self.modbus_serial and self.modbus_serial.is_connected()
        ])
        self.connected_logo = bool(self.logo and self.logo.is_connected())
        if self.connected != prev_connected or self.connected_logo != prev_connected_logo:
            try:
                status = "online" if self.connected else "offline"
                logo_status = "online" if self.connected_logo else "offline"
                self.mqtt.on_change_device_connection(self.serial, status, logo_status)
            except Exception as e:
                self.log(f"❌ Error notificando conexión de {self.name}: {e}")
        

    def start(self) -> None:
        """Start all per-device connections according to connectionConfig."""
        # Always try to start LOGO.
        if self.cc.get("logoIp") and self.cc.get("logoPort"):
            try:
                if self.logo:
                    self.logo.start()
            except Exception as e:
                self.log(f"⚠️ Error starting LOGO: {e}")

        reader = self.cc.get("defaultReader")
        try:
            if reader == "serial" and self.modbus_serial:
                self.modbus_serial.start()
            elif reader == "tcp" and self.modbus_tcp:
                self.modbus_tcp.start()
            elif reader == "http" and self.http:
                self.http.start()
        except Exception as e:
            self.log(f"⚠️ Error starting {reader}: {e}")

        print(f"▶️ Conectando dispositivo {self.name}")
        self.update_connected()

    def turn_on(self):
        changed = False
        if self.cc["mode"] == "remote":
            if self.modbus_tcp.is_connected():
                changed = self.modbus_tcp.turn_on()
            if not changed and self.modbus_serial.is_connected():
                changed = self.modbus_serial.turn_on()
        elif self.cc["mode"] == "local":
            if self.logo.is_connected():
                changed = self.logo.turn_on()
        print(f"Probando encender con {self.cc['mode']}: {changed}")


    def turn_off(self):
        changed = False
        if self.cc["mode"] == "remote":
            if self.modbus_tcp.is_connected():
                changed = self.modbus_tcp.turn_off()
            if not changed and self.modbus_serial.is_connected():
                changed = self.modbus_serial.turn_off()
        elif self.cc["mode"] == "local":
            if self.logo.is_connected():
                changed = self.logo.turn_off()
        print(f"Probando apagar con {self.cc['mode']}: {changed}")


    def set_local(self):
        changed = self.modbus_serial.set_local()
        if not changed:
            self.modbus_tcp.set_local()

    def set_remote(self):
        changed = self.modbus_serial.set_remote()
        if not changed:
            self.modbus_tcp.set_remote()

    def restart(self):
        changed = False
        if self.cc["mode"] == "remote":
            if self.modbus_tcp.is_connected():
                changed = self.modbus_tcp.restart()
            if not changed and self.modbus_serial.is_connected():
                changed = self.modbus_serial.restart()
        elif self.cc["mode"] == "local":
            if self.logo.is_connected():
                changed = self.logo.restart()
        print(f"Probando reiniciar con {self.cc['mode']}: {changed}")

    def execute_command(self, command_name: str, channel: str | None = None, value_name: str = "on") -> bool:
        command_key = (command_name or "").strip()
        command_alias = command_key.lower()

        if command_alias == "turnon":
            self.turn_on()
            return True
        if command_alias == "turnoff":
            self.turn_off()
            return True
        if command_alias == "restart" and not channel:
            self.restart()
            return True

        if channel == "logo":
            if self.logo and self.logo.is_connected():
                return self.logo.execute_command(command_key, value_name)
            return False

        if channel == "drive":
            if self.modbus_tcp and self.modbus_tcp.is_connected():
                return self.modbus_tcp.execute_command(command_key, value_name)
            if self.modbus_serial and self.modbus_serial.is_connected():
                return self.modbus_serial.execute_command(command_key, value_name)
            return False

        if self.cc.get("mode") == "local" and self.logo and self.logo.is_connected():
            return self.logo.execute_command(command_key, value_name)

        if self.modbus_tcp and self.modbus_tcp.is_connected():
            return self.modbus_tcp.execute_command(command_key, value_name)
        if self.modbus_serial and self.modbus_serial.is_connected():
            return self.modbus_serial.execute_command(command_key, value_name)
        if self.logo and self.logo.is_connected():
            return self.logo.execute_command(command_key, value_name)

        return False

    # ---------------------------
    # Connection helpers (connect/disconnect)
    # ---------------------------

    # Http
    # def connect_http(self) -> None:
    #     if self.cc.get("host") and self.cc.get("httpPort"):
    #         try:
    #             self.http.connect(base_url=self.base_url, interval=self.http_interval)
    #             self.log(f"🌐 HTTP connected: {self.base_url} ({self.device_id})")
    #         except Exception as e:
    #             self.log(f"⚠️ HTTP error ({self.device_id}): {e}")

    # def disconnect_http(self) -> None:
    #     if self.http and hasattr(self.http, "stop"):
    #         try:
    #             self.http.stop()
    #         except Exception:
    #             pass

    # ---------------------------
    # Hot config update (reuses helpers)
    # ---------------------------
    def update_connection_config(self, new_cfg: Dict[str, Any]) -> None:
        """
        Update self.cc (connectionConfig) and restart only the connections that changed.
        """
        self.log(f"Actualizando configuración del dispositivo {self.serial}")
        if not isinstance(new_cfg, dict):
            self.log("update_connection_config: argumento inválido (dict esperado).")
            return

        with self._lock:
            # Keep only allowed keys.
            filtered = {k: v for k, v in new_cfg.items() if k in self._ALLOWED_CC_KEYS}
            if not filtered:
                self.log("ℹ️ update_connection_config: no hay cambios aplicables.")
                return

            prev = dict(self.cc)

            # Partial merge: add/update values or remove keys when None is received.
            for k, v in filtered.items():
                if v is None and k in self.cc:
                    del self.cc[k]
                elif v is not None:
                    self.cc[k] = v

            # Detect changes.
            changed_tcp    = any(prev.get(k) != self.cc.get(k) for k in ("host", "tcpPort", "slaveId"))
            changed_serial = any(prev.get(k) != self.cc.get(k) for k in ("serialPort", "baudrate", "slaveId"))
            changed_logo   = any(prev.get(k) != self.cc.get(k) for k in ("logoIp", "logoPort"))
            changed_mode   = prev.get("mode") != self.cc.get("mode")

            # Apply changes.
            if changed_tcp:
                self.log(f"♻️ Reiniciando Modbus TCP ({self.device_id}) por cambio de configuración.")
                self.modbus_tcp.update_config(
                    self.cc.get("host"),
                    self.cc.get("tcpPort"),
                    self.cc.get("slaveId")
                )

            if changed_serial:
                self.log(f"♻️ Reiniciando Modbus Serial ({self.device_id}) por cambio de configuración.")
                self.modbus_serial.update_config(
                    self.cc.get("serialPort"),
                    self.cc.get("baudrate"),
                    self.cc.get("slaveId")
                )

            if changed_logo:
                self.log(f"♻️ Reiniciando LOGO! ({self.device_id}) por cambio de configuración.")
                self.logo.update_config(
                    self.cc.get("logoIp"),
                    self.cc.get("logoPort")
                )

            if changed_mode:
                self.log(f"♻️ Modo cambiado a {self.cc.get('mode')}")
                if self.cc.get("mode") == "local":
                    self.set_local()
                else:
                    self.set_remote()

            if not any((changed_tcp, changed_serial, changed_logo, changed_mode)):
                self.log("ℹ️ update_connection_config: no hubo cambios efectivos.")

        # Notify the update.
        self.update_fields(self)

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
                self.log("⚠️ Empty result; MQTT will not be sent.")
                return
            org_id, gw_id = self._ids()
            if not org_id or not gw_id:
                self.log(f"⚠️ Missing IDs in gateway_cfg: org={org_id} gw={gw_id}")
                return
            topic_info = {
                "serial_number":  self.serial,
                "organization_id": org_id,
                "gateway_id":      gw_id,
            }
            payload = {"group": group, "payload": results}
            self.mqtt.send_signal(topic_info, payload)
        except Exception as e:
            self.log(f"❌ DeviceService._send_signal error ({self.device_id}): {e}")
