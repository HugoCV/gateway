# device_service.py
import threading
import time
from typing import Dict, Any, Optional, Tuple
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
        self.http = None
        self.modbus_tcp: Optional[ModbusTcp] = None
        self.modbus_serial: Optional[ModbusSerial] = None
        self.logo: Optional[LogoModbusClient] = None
        self.direct_responsive = False
        self.direct_connection_reason = "awaiting_modbus_response"
        self.direct_failed_registers = []
        self._last_published_connection_state = None

        # self.base_url = f"http://{self.cc['host']}:{self.cc['httpPort']}/api/dashboard"
        # self.http = HttpClient(self, self._send_signal, self.log)
        self._normalize_connection_config()
        self._create_connection_clients()
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

    def _normalize_connection_config(self) -> None:
        """Fill safe defaults for optional connection settings."""
        self.cc.setdefault("baudrate", 9600)
        self.cc.setdefault("slaveId", 1)
        self.cc.setdefault("mode", "remote")

    def _create_connection_clients(self) -> None:
        serial_port = self.cc.get("serialPort")
        baudrate = self.cc.get("baudrate")
        slave_id = self.cc.get("slaveId")
        host = self.cc.get("host")
        tcp_port = self.cc.get("tcpPort")
        logo_ip = self.cc.get("logoIp")
        logo_port = self.cc.get("logoPort")

        if serial_port:
            self.modbus_serial = ModbusSerial(
                self,
                self._send_signal,
                self.log,
                serial_port,
                baudrate,
                slave_id,
            )
        else:
            self.log(f"ℹ️ {self.name}: conexión Modbus Serial no configurada.")

        if host and tcp_port:
            self.modbus_tcp = ModbusTcp(
                self,
                self._send_signal,
                self.log,
                host,
                tcp_port,
                slave_id,
            )
        else:
            self.log(f"ℹ️ {self.name}: conexión Modbus TCP no configurada.")

        if logo_ip and logo_port:
            self.logo = LogoModbusClient(
                self,
                self.log,
                self._send_signal,
                logo_ip,
                logo_port,
            )

    def update_direct_connection(
        self,
        responsive: bool,
        reason: str | None = None,
        failed_registers=None,
    ) -> None:
        self.direct_responsive = responsive
        self.direct_connection_reason = reason
        self.direct_failed_registers = (
            list(failed_registers)
            if isinstance(failed_registers, list)
            else []
        )
        self.update_connected()

    def update_connected(self) -> None:
        """Publish route status based on device responses, not only open transports."""
        self.connected = self.direct_responsive
        self.connected_logo = bool(self.logo and self.logo.is_connected())
        connection_state = (
            self.connected,
            self.connected_logo,
            self.direct_connection_reason,
            tuple(
                (register.get("name"), register.get("address"))
                for register in self.direct_failed_registers
            ),
        )
        if connection_state != self._last_published_connection_state:
            try:
                status = "online" if self.connected else "offline"
                logo_status = "online" if self.connected_logo else "offline"
                self.mqtt.on_change_device_connection(
                    self.serial,
                    status,
                    logo_status,
                    self.direct_connection_reason,
                    "direct",
                    self.direct_failed_registers,
                )
                self._last_published_connection_state = connection_state
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
        if self.cc.get("mode", "remote") == "remote":
            if self.modbus_tcp and self.modbus_tcp.is_connected():
                changed = self.modbus_tcp.turn_on()
            if not changed and self.modbus_serial and self.modbus_serial.is_connected():
                changed = self.modbus_serial.turn_on()
        elif self.cc.get("mode") == "local":
            if self.logo and self.logo.is_connected():
                changed = self.logo.turn_on()
        print(f"Probando encender con {self.cc.get('mode')}: {changed}")
        return bool(changed)

    def turn_off(self):
        changed = False
        if self.cc.get("mode", "remote") == "remote":
            if self.modbus_tcp and self.modbus_tcp.is_connected():
                changed = self.modbus_tcp.turn_off()
            if not changed and self.modbus_serial and self.modbus_serial.is_connected():
                changed = self.modbus_serial.turn_off()
        elif self.cc.get("mode") == "local":
            if self.logo and self.logo.is_connected():
                changed = self.logo.turn_off()
        print(f"Probando apagar con {self.cc.get('mode')}: {changed}")
        return bool(changed)

    def set_local(self):
        changed = False
        if self.modbus_serial:
            changed = self.modbus_serial.set_local()
        if not changed and self.modbus_tcp:
            self.modbus_tcp.set_local()

    def set_remote(self):
        changed = False
        if self.modbus_serial:
            changed = self.modbus_serial.set_remote()
        if not changed and self.modbus_tcp:
            self.modbus_tcp.set_remote()

    def restart(self):
        changed = False
        if self.cc.get("mode", "remote") == "remote":
            if self.modbus_tcp and self.modbus_tcp.is_connected():
                changed = self.modbus_tcp.restart()
            if not changed and self.modbus_serial and self.modbus_serial.is_connected():
                changed = self.modbus_serial.restart()
        elif self.cc.get("mode") == "local":
            if self.logo and self.logo.is_connected():
                changed = self.logo.restart()
        print(f"Probando reiniciar con {self.cc.get('mode')}: {changed}")
        return bool(changed)

    def execute_command(self, command_name: str, channel: str | None = None, value_name: str = "on") -> bool:
        command_key = (command_name or "").strip()
        command_alias = command_key.lower()

        if command_alias == "turnon":
            return self.turn_on()
        if command_alias == "turnoff":
            return self.turn_off()
        if command_alias == "restart" and not channel:
            return self.restart()

        if channel == "logo":
            if self.logo and self.logo.is_connected():
                return self.logo.execute_command(command_key, value_name)
            return False

        if channel == "direct":
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

    @staticmethod
    def _values_equal(left, right) -> bool:
        if type(left) is type(right):
            return left == right
        try:
            return float(left) == float(right)
        except (TypeError, ValueError):
            return str(left) == str(right)

    @classmethod
    def _condition_is_active(cls, raw_value, condition: Dict[str, Any]) -> bool:
        operator = condition.get("operator")
        value = condition.get("value")
        values = condition.get("values") or []

        if operator == "equals":
            return cls._values_equal(raw_value, value)
        if operator == "notEquals":
            return not cls._values_equal(raw_value, value)
        if operator == "in":
            return any(cls._values_equal(raw_value, item) for item in values)
        if operator == "notIn":
            return not any(cls._values_equal(raw_value, item) for item in values)
        if operator == "greaterThan":
            try:
                return float(raw_value) > float(value)
            except (TypeError, ValueError):
                return False
        if operator == "lessThan":
            try:
                return float(raw_value) < float(value)
            except (TypeError, ValueError):
                return False
        if operator == "bitSet":
            try:
                return (int(raw_value) & int(value)) == int(value)
            except (TypeError, ValueError):
                return False
        return False

    def _get_channel_config(self, channel: Optional[str]) -> Tuple[str, Optional[Dict[str, Any]]]:
        channel_key = channel or "direct"
        modbus_config = self.device.get("modbusConfig")
        channels = (
            modbus_config.get("channels")
            if isinstance(modbus_config, dict)
            else None
        )
        if not isinstance(channels, dict):
            return channel_key, None
        config = channels.get(channel_key)
        return channel_key, config if isinstance(config, dict) else None

    def _read_channel_register(
        self, channel: str, config: Dict[str, Any], address: int
    ):
        if channel == "logo":
            if not self.logo or not self.logo.is_connected():
                return None
            values = self.logo.read_registers(address, 1)
            return values[0] if values else None

        protocol = config.get("protocol")
        if protocol == "modbus-tcp":
            if not self.modbus_tcp or not self.modbus_tcp.is_connected():
                return None
            values = self.modbus_tcp.read_holding_registers(address, count=1)
            return values[0] if values else None

        if protocol == "modbus-rtu":
            if not self.modbus_serial or not self.modbus_serial.is_connected():
                return None
            values = self.modbus_serial.read_holding_registers(address, count=1)
            return values[0] if values else None

        return None

    def _get_fault_checks(
        self, config: Dict[str, Any]
    ) -> list[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]]:
        registers = config.get("registers")
        events = config.get("events")
        if not isinstance(registers, dict):
            return []

        checks = []
        if isinstance(events, dict):
            for rule in events.values():
                if not isinstance(rule, dict) or rule.get("type") != "fault":
                    continue
                register = registers.get(rule.get("signal"))
                if isinstance(register, dict):
                    checks.append((register, rule.get("activeWhen")))

        if checks:
            return checks

        # Configuraciones existentes pueden expresar el estado seguro mediante
        # el significado del registro, sin asumir que un número fijo es "sin falla".
        fault_register = registers.get("fault")
        if not isinstance(fault_register, dict):
            return []
        types = fault_register.get("types")
        if not isinstance(types, dict):
            return []

        safe_meanings = {"none", "no fault", "sin falla", "ninguna", "ok"}
        safe_values = [
            raw_value
            for raw_value, meaning in types.items()
            if str(meaning).strip().lower() in safe_meanings
        ]
        if not safe_values:
            return []

        return [(fault_register, {"operator": "notIn", "values": safe_values})]

    def verify_faults_cleared(
        self,
        channel: Optional[str],
        attempts: int = 6,
        interval: float = 0.5,
    ) -> Tuple[bool, Optional[str]]:
        channel_key, config = self._get_channel_config(channel)
        if not config:
            return True, None

        checks = self._get_fault_checks(config)
        if not checks:
            return True, None

        saw_response = False
        saw_active_fault = False
        consecutive_clear_reads = 0
        for _ in range(attempts):
            active_fault = False
            complete_read = True

            for register, condition in checks:
                try:
                    address = int(register["address"])
                except (KeyError, TypeError, ValueError):
                    complete_read = False
                    continue

                raw_value = self._read_channel_register(
                    channel_key, config, address
                )
                if raw_value is None:
                    complete_read = False
                    continue

                saw_response = True
                if self._condition_is_active(raw_value, condition or {}):
                    active_fault = True
                    saw_active_fault = True

            if complete_read and not active_fault:
                consecutive_clear_reads += 1
                if consecutive_clear_reads >= 2:
                    return True, None
            else:
                consecutive_clear_reads = 0
            time.sleep(interval)

        if not saw_response:
            return False, "verification_read_failed"
        if saw_active_fault:
            return False, "fault_still_active"
        return False, "verification_read_failed"

    def execute_command_with_confirmation(
        self,
        command_name: str,
        channel: Optional[str] = None,
        value_name: str = "on",
    ) -> Tuple[bool, Optional[str]]:
        succeeded = self.execute_command(command_name, channel, value_name)
        if not succeeded:
            return False, "device_write_failed"

        if (command_name or "").strip().lower() == "restart":
            return self.verify_faults_cleared(channel)

        return True, None

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
            self._normalize_connection_config()

            # Detect changes.
            changed_tcp    = any(prev.get(k) != self.cc.get(k) for k in ("host", "tcpPort", "slaveId"))
            changed_serial = any(prev.get(k) != self.cc.get(k) for k in ("serialPort", "baudrate", "slaveId"))
            changed_logo   = any(prev.get(k) != self.cc.get(k) for k in ("logoIp", "logoPort"))
            changed_mode   = prev.get("mode") != self.cc.get("mode")

            # Apply changes.
            if changed_tcp:
                self.log(f"♻️ Reiniciando Modbus TCP ({self.device_id}) por cambio de configuración.")
                has_tcp_config = bool(self.cc.get("host") and self.cc.get("tcpPort"))
                if self.modbus_tcp and has_tcp_config:
                    self.modbus_tcp.update_config(
                        self.cc.get("host"),
                        self.cc.get("tcpPort"),
                        self.cc.get("slaveId")
                    )
                elif self.modbus_tcp and not has_tcp_config:
                    self.modbus_tcp.stop()
                    self.modbus_tcp = None
                elif has_tcp_config:
                    self.modbus_tcp = ModbusTcp(
                        self,
                        self._send_signal,
                        self.log,
                        self.cc.get("host"),
                        self.cc.get("tcpPort"),
                        self.cc.get("slaveId"),
                    )
                    self.modbus_tcp.start()

            if changed_serial:
                self.log(f"♻️ Reiniciando Modbus Serial ({self.device_id}) por cambio de configuración.")
                has_serial_config = bool(self.cc.get("serialPort"))
                if self.modbus_serial and has_serial_config:
                    self.modbus_serial.update_config(
                        self.cc.get("serialPort"),
                        self.cc.get("baudrate"),
                        self.cc.get("slaveId")
                    )
                elif self.modbus_serial and not has_serial_config:
                    self.modbus_serial.stop()
                    self.modbus_serial = None
                elif has_serial_config:
                    self.modbus_serial = ModbusSerial(
                        self,
                        self._send_signal,
                        self.log,
                        self.cc.get("serialPort"),
                        self.cc.get("baudrate"),
                        self.cc.get("slaveId"),
                    )
                    self.modbus_serial.start()

            if changed_logo:
                self.log(f"♻️ Reiniciando LOGO! ({self.device_id}) por cambio de configuración.")
                has_logo_config = bool(self.cc.get("logoIp") and self.cc.get("logoPort"))
                if self.logo and has_logo_config:
                    self.logo.update_config(
                        self.cc.get("logoIp"),
                        self.cc.get("logoPort")
                    )
                elif self.logo and not has_logo_config:
                    self.logo.stop()
                    self.logo = None
                elif has_logo_config:
                    self.logo = LogoModbusClient(
                        self,
                        self.log,
                        self._send_signal,
                        self.cc.get("logoIp"),
                        self.cc.get("logoPort"),
                    )
                    self.logo.start()

            if changed_mode:
                self.log(f"♻️ Modo cambiado a {self.cc.get('mode')}")
                if self.cc.get("mode") == "local":
                    self.set_local()
                else:
                    self.set_remote()

            if not any((changed_tcp, changed_serial, changed_logo, changed_mode)):
                self.log("ℹ️ update_connection_config: no hubo cambios efectivos.")

        # Notify the update.
        if self.update_fields:
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
