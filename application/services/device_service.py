# device_service.py
from typing import Dict, Any, Optional
from threading import RLock

from infrastructure.http.http_client import HttpClient
from infrastructure.logo.logo_client import LogoModbusClient
from infrastructure.modbus.modbus_tcp import ModbusTcp
from infrastructure.modbus.modbus_serial import ModbusSerial



# Escalas por clave (aplican si la clave existe y el valor no es None)

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
        self.http_interval =0.5

        # Allowed connectionConfig keys
        self._ALLOWED_CC_KEYS = {
            "host", "httpPort", "tcpPort",
            "serialPort", "baudrate", "slaveId",
            "logoIp", "logoPort"
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

        base_url = f"http://{self.cc['host']}:{self.cc['httpPort']}/api/dashboard"
        self.http = HttpClient(self, self._send_signal, self.log)
        self.modbus_serial = ModbusSerial(self, self._send_signal, self.log)
        self.modbus_tcp = ModbusTcp(self, self._send_signal, self.log)
        self.logo = LogoModbusClient(self, self.log, self._send_signal)

        self.alive: bool = False

    # ---------------------------
    # Lifecycle
    # ---------------------------
    def start(self) -> None:
        """Create per-device connections according to its connectionConfig."""
        if not self.device_id:
            self.log("⚠️ DeviceService: device without identifier.")
            return

        org_id, gw_id = self._ids()
        if not org_id or not gw_id:
            self.log("⚠️ DeviceService: missing organizationId/gatewayId.")
            return

        self.alive = True
        self.log(f"▶️ Starting DeviceService for {self.device_id}")

        if not any([self.http, self.modbus_tcp, self.modbus_serial, self.logo]):
            self.log(f"⚠️ {self.device_id} has no configured endpoints (HTTP/TCP/Serial/LOGO).")

    def stop(self) -> None:
        """Best-effort to stop device connections."""
        self.alive = False
        self.log(f"⏹️ Stopping DeviceService for {self.device_id}")

    def turn_off(self):
        changed = False
        if(self.modbus_tcp.is_connected()):
            changed = self.modbus_tcp.turn_off()
        if(self.modbus_serial.is_connected() and not changed):
            changed = self.modbus_serial.turn_off()
        if(changed):
            return self.log(f"se apago el dispositivo {self.name}")
        return self.log(f"No se pudo apagar el dispositivo {self.name}")

    def turn_on(self):
        changed = False
        if(self.modbus_tcp.is_connected()):
            changed = self.modbus_tcp.turn_on()
        if(self.modbus_serial.is_connected() and not changed):
            changed = self.modbus_serial.turn_on()
        if(changed):
            return self.log(f"se encendio el dispositvio {self.name}")
        return self.log(f"No se pudo encender el dispositvio {self.name}")


    def disconnect_all_devices(self) -> None:
        """
        Disconnect all device services.
        """
        self.log("⏹️ Desconectando...")
        dev_service.stop()
        dev_service.disconnect_http()
        dev_service.disconnect_modbus_tcp()
        dev_service.disconnect_modbus_serial()
        dev_service.disconnect_logo()
        self.log("✅ Desconectado.")

    # ---------------------------
    # Connection helpers (connect/disconnect)
    # ---------------------------

    # Http
    def connect_http(self) -> None:
        if self.cc.get("host") and self.cc.get("httpPort"):
            try:
                self.http.connect(base_url=base_url, interval=self.http_interval)
                self.log(f"🌐 HTTP connected: {base_url} ({self.device_id})")
            except Exception as e:
                self.log(f"⚠️ HTTP error ({self.device_id}): {e}")

    def disconnect_http(self) -> None:
        if self.http and hasattr(self.http, "stop"):
            try:
                self.http.stop()
            except Exception:
                pass
        self.http = None

    def start_reading_http(self):
        if(self.http):
            self.http.start_continuous_read()

    # TCP
    def start_reading_modbus_tcp(self)-> None:
        self.modbus_tcp.start_reading()

    def disconnect_modbus_tcp(self) -> None:
        if self.modbus_tcp and hasattr(self.modbus_tcp, "stop"):
            try:
                self.modbus_tcp.stop()
            except Exception:
                pass
    
    def connect_modbus_tcp(self) -> None:
        if self.cc.get("host") and self.cc.get("tcpPort") and self.cc.get("slaveId"):
            try:
                self.modbus_tcp.connect(self.cc["host"], self.cc["tcpPort"], self.cc["slaveId"])
                self.log(f"🔌 Modbus TCP connected: {self.cc['host']}:{self.cc['tcpPort']} ({self.device_id})")
            except Exception as e:
                self.log(f"⚠️ Modbus TCP error ({self.device_id}): {e}")
    def turn_on_modbus_tcp(self):
        self.modbus_tcp.turn_on()

    def turn_off_modbus_tcp(self):
        self.modbus_tcp.turn_off()

    def restart_modbus_seial(self):
        self.modbus_tcp.restart()


    # Serial
    def connect_modbus_serial(self) -> None:
        print("connect_modbus_serial", self.modbus_serial)
        if self.cc.get("serialPort") and self.cc.get("baudrate") and self.cc.get("slaveId") is not None:
            try:
                self.modbus_serial.connect(
                    port=self.cc["serialPort"],
                    baudrate=self.cc["baudrate"],
                    slave_id=self.cc["slaveId"],
                )
            except Exception as e:
                self.log(f"⚠️ Modbus Serial error ({self.device_id}): {e}")
    
    def disconnect_modbus_serial(self) -> None:
        if self.modbus_serial and hasattr(self.modbus_serial, "stop"):
            try:
                self.modbus_serial.stop()
            except Exception:
                pass

    def start_reading_modbus_serial(self):
        self.modbus_serial.start_reading()

    def turn_on_modbus_serial(self):
        self.modbus_serial.turn_on()

    def turn_off_modbus_serial(self):
        self.modbus_serial.turn_off()
    

    # Logo
    def connect_logo(self) -> None:
        if self.cc.get("logoIp") and self.cc.get("logoPort"):
            try:
                self.logo.connect(host=self.cc["logoIp"], port=self.cc["logoPort"])
                self.log(f"🧱 LOGO connected: {self.cc['logoIp']}:{self.cc['logoPort']} ({self.device_id})")
            except Exception as e:
                self.log(f"⚠️ LOGO error ({self.device_id}): {e}")

    def start_reading_logo(self) -> None:
        if(self.logo):
            self.logo.start_reading()

    def disconnect_logo(self) -> None:
        if self.logo and hasattr(self.logo, "stop"):
            try:
                self.logo.stop()
            except Exception:
                pass
        self.logo = None

    # ---------------------------
    # Hot config update (reuses helpers)
    # ---------------------------
    def update_connection_config(self, new_cfg: Dict[str, Any]) -> None:
        """
        Update self.cc (connectionConfig) and restart only the connections that changed.
        """
        self.log(f"Se actualizarion las conexiones del dispositivo {self.serial}")
        if not isinstance(new_cfg, dict):
            self.log("⚠️ update_connection_config: invalid argument (dict expected).")
            return

        with self._lock:
            filtered = {k: v for k, v in new_cfg.items() if k in self._ALLOWED_CC_KEYS}
            if not filtered:
                self.log("update_connection_config: no applicable changes.")
                return

            prev = dict(self.cc)

            # Merge (partial): new/updated keys; None values remove key
            for k, v in filtered.items():
                if v is None and k in self.cc:
                    del self.cc[k]
                elif v is not None:
                    self.cc[k] = v

            # changed_http = any(prev.get(k) != self.cc.get(k) for k in ("host", "httpPort"))
            # changed_tcp  = any(prev.get(k) != self.cc.get(k) for k in ("host", "tcpPort"))
            # changed_ser  = any(prev.get(k) != self.cc.get(k) for k in ("serialPort", "baudrate", "slaveId"))
            # changed_logo = any(prev.get(k) != self.cc.get(k) for k in ("logoIp", "logoPort"))

            # if changed_http:
            #     self.log(f"Restarting HTTP ({self.device_id}) due to config change.")
            #     self._stop_http(); self._start_http()

            # if changed_tcp:
            #     self.log(f"Restarting Modbus TCP ({self.device_id}) due to config change.")
            #     self._stop_modbus_tcp(); self._start_modbus_tcp()

            # if changed_ser:
            #     self.log(f"Restarting Modbus Serial ({self.device_id}) due to config change.")
            #     self._stop_modbus_serial(); self.start_modbus_serial()

            # if changed_logo:
            #     self.log(f"Restarting LOGO! ({self.device_id}) due to config change.")
            #     self._stop_logo(); self._start_logo()

            # if not any((changed_http, changed_tcp, changed_ser, changed_logo)):
            #     self.log("ℹupdate_connection_config: no effective changes in endpoints.")
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
            print("results", results)
            payload = {"group": group, "payload": results}
            self.mqtt.send_signal(topic_info, payload)
        except Exception as e:
            self.log(f"❌ DeviceService._send_signal error ({self.device_id}): {e}")
