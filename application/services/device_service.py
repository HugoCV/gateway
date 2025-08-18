# device_service.py
from typing import Dict, Any, Optional
from threading import RLock

from infrastructure.http.http_client import HttpClient
from infrastructure.logo.logo_client import LogoModbusClient
from infrastructure.modbus.modbus_tcp import ModbusTcp
from infrastructure.modbus.modbus_serial import ModbusSerial


SIGNAL_MODBUS_SERIAL_DIR = {
    "freqRef": 4,
    "accTime": 6,
    "decTime": 7,
    "curr": 8,
    "freq": 9,
    "volt": 10,
    "power": 12,
    "stat": 16,
    "dir": 16,         # si cambia, actualiza aquí
    "speed": 785,
    "alarm": 815,
    "temp": 860,
}

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
        signal_modbus_tcp_dir: Dict[str, int],
        signal_logo_dir: Dict[str, int],
        modbus_scales: Dict[str, float],
        modbus_labels: Dict[str, str],
        logo_labels: Dict[str, str],
        update_fields,
        http_interval: float = 5.0,
        poll_interval: float = 0.5,
    ) -> None:
        self.mqtt = mqtt_handler
        self.gateway_cfg = gateway_cfg
        self.device = device or {}
        self.log = log
        self.update_fields = update_fields
        self._lock = RLock()

        # Allowed connectionConfig keys
        self._ALLOWED_CC_KEYS = {
            "host", "httpPort", "tcpPort",
            "serialPort", "baudrate", "slaveId",
            "logoIp", "logoPort"
        }

        self.signal_modbus_tcp_dir = signal_modbus_tcp_dir
        self.signal_logo_dir = signal_logo_dir
        self.modbus_scales = modbus_scales
        self.modbus_labels = modbus_labels
        self.logo_labels = logo_labels

        self.http_interval = http_interval
        self.poll_interval = poll_interval

        # Device identity
        self.device_id: str = (
            self.device.get("_id")
            or self.device.get("serialNumber")
            or self.device.get("name")
            or ""
        )
        self.model: str = self.device.get("deviceModel", "")
        self.serial: str = self.device.get("serialNumber", "")
        self.cc: Dict[str, Any] = self.device.get("connectionConfig") or {}

        # Per-device handlers
        self.http: Optional[HttpClient] = None
        self.modbus_tcp: Optional[ModbusTcp] = None
        self.modbus_serial: Optional[ModbusSerial] = None
        self.logo: Optional[LogoModbusClient] = None

        # Polling handlers
        self.tcp_poll = None
        self.serial_poll = None

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

        # Use the same helpers that update_connection_config uses
        self._stop_all()  # ensure a clean start if called twice
        # self._start_http()
        # self._start_modbus_tcp()
        # self._start_modbus_serial()
        # self._start_logo()

        if not any([self.http, self.modbus_tcp, self.modbus_serial, self.logo]):
            self.log(f"⚠️ {self.device_id} has no configured endpoints (HTTP/TCP/Serial/LOGO).")

    def connect_http(self) -> None:
        host = self.cc.get("host")
        port = self.cc.get("httpPort")
        if not host or port in (None, ""):
            self.log("⚠️ HTTP host/port not set in connectionConfig.")
            return
        print("connectando a http")
        self._stop_http()
        self._start_http()

    def stop(self) -> None:
        """Best-effort to stop device connections."""
        self.alive = False
        self.log(f"⏹️ Stopping DeviceService for {self.device_id}")
        self._stop_all()

    # ---------------------------
    # Connection helpers (start/stop)
    # ---------------------------
    def _stop_all(self) -> None:
        self._stop_http()
        self._stop_modbus_tcp()
        self._stop_modbus_serial()
        self._stop_logo()
        self.tcp_poll = None
        self.serial_poll = None

    # def connect_http(self) -> None:
    #     if self.cc.get("host") and self.cc.get("httpPort"):
    #         try:
    #             base_url = f"http://{self.cc['host']}:{self.cc['httpPort']}/api/dashboard"
    #             self.http = HttpClient(self, self._on_http_read, self.log)
    #             self.http.connect(base_url=base_url, interval=self.http_interval)
    #             self.http.start_continuous_read()
    #             self.log(f"🌐 HTTP connected: {base_url} ({self.device_id})")
    #         except Exception as e:
    #             self.log(f"⚠️ HTTP error ({self.device_id}): {e}")

    def disconnect_http(self) -> None:
        if self.http and hasattr(self.http, "stop"):
            try:
                self.http.stop()
            except Exception:
                pass
        self.http = None

    def connect_modbus_tcp(self) -> None:
        if self.cc.get("host") and self.cc.get("tcpPort"):
            try:
                self.modbus_tcp = ModbusTcp(self, self._on_modbus_tcp_read, self.log)
                self.modbus_tcp.connect(self.cc["host"], self.cc["tcpPort"])
                # Local mode by default in your app
                if hasattr(self.modbus_tcp, "set_local"):
                    self.modbus_tcp.set_local()
                addrs = list(dict.fromkeys(self.signal_modbus_tcp_dir.values()))
                self.tcp_poll = self.modbus_tcp.poll_registers(
                    addresses=addrs, interval=self.poll_interval
                )
                self.log(f"🔌 Modbus TCP connected: {self.cc['host']}:{self.cc['tcpPort']} ({self.device_id})")
            except Exception as e:
                self.log(f"⚠️ Modbus TCP error ({self.device_id}): {e}")
                
    def start_modebus_tcp(self)-> None:

    def disconnect_modbus_tcp(self) -> None:
        if self.modbus_tcp and hasattr(self.modbus_tcp, "stop"):
            try:
                self.modbus_tcp.stop()
            except Exception:
                pass
        self.modbus_tcp = None
        self.tcp_poll = None

    def connect_modbus_serial(self) -> None:
        if self.cc.get("serialPort") and self.cc.get("baudrate") and self.cc.get("slaveId") is not None:
            try:
                self.modbus_serial = ModbusSerial(self, self.callback_signal, self.log)
                self.modbus_serial.connect(
                    port=self.cc["serialPort"],
                    baudrate=self.cc["baudrate"],
                    slave_id=self.cc["slaveId"],
                )
            except Exception as e:
                self.log(f"⚠️ Modbus Serial error ({self.device_id}): {e}")

    def callback_signal(self, signal, device):
        print(signal, device)


    def multiple_modbus_serial_read(self):
        addrs = list(dict.fromkeys(SIGNAL_MODBUS_SERIAL_DIR.values()))
        self.serial_poll = self.modbus_serial.poll_registers(
            addresses=addrs, interval=self.poll_interval
        )
        self.log(
            f"🧵 Modbus Serial connected: {self.cc['serialPort']}@{self.cc['baudrate']} "
            f"(sid={self.cc['slaveId']}) ({self.device_id})"
        )

    def _stop_modbus_serial(self) -> None:
        if self.modbus_serial and hasattr(self.modbus_serial, "stop"):
            try:
                self.modbus_serial.stop()
            except Exception:
                pass
        self.modbus_serial = None
        self.serial_poll = None

    def _start_logo(self) -> None:
        if self.cc.get("logoIp") and self.cc.get("logoPort"):
            try:
                self.logo = LogoModbusClient(self, self.log, self._on_logo_read)
                self.logo.connect(host=self.cc["logoIp"], port=self.cc["logoPort"])
                addrs = list(dict.fromkeys(self.signal_logo_dir.values()))
                self.logo.poll_registers(addrs)
                self.log(f"🧱 LOGO connected: {self.cc['logoIp']}:{self.cc['logoPort']} ({self.device_id})")
            except Exception as e:
                self.log(f"⚠️ LOGO error ({self.device_id}): {e}")

    def _stop_logo(self) -> None:
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
        print("configuracion actual",self.cc)

    # ---------------------------
    # Read callbacks
    # ---------------------------
    def _on_http_read(self, results: Dict[str, Any]) -> None:
        # Publishes HTTP readings as 'drive' group
        self._send_signal("drive", results)

    def _on_modbus_tcp_read(self, regs: Dict[int, int]) -> None:
        signal = self._build_signal_from_regs(regs, self.signal_modbus_tcp_dir)
        for k, label in self.modbus_labels.items():
            v = signal.get(k)
            if v is not None:
                self.log(f"ℹ️ [{self.device_id}] {label}: {v}")
        self._send_signal("drive", signal)

    def _on_modbus_serial_read(self, regs: Dict[int, int]) -> None:
        signal = self._build_signal_from_regs(regs, SIGNAL_MODBUS_SERIAL_DIR)
        for k, label in self.modbus_labels.items():
            v = signal.get(k)
            if v is not None:
                self.log(f"ℹ️ [{self.device_id}] {label}: {v}")
        self._send_signal("drive", signal)

    def _on_logo_read(self, regs: Dict[int, int]) -> None:
        signal = {name: regs.get(addr) for name, addr in self.signal_logo_dir.items()}
        for k, label in self.logo_labels.items():
            v = signal.get(k)
            if v is not None:
                self.log(f"ℹ️ [{self.device_id}] {label}: {v}")
        self._send_signal("logo", signal)

    # ---------------------------
    # Internal helpers
    # ---------------------------
    def _ids(self):
        org_id = self.gateway_cfg.get("organization_id") or self.gateway_cfg.get("organizationId")
        gw_id  = self.gateway_cfg.get("gateway_id") or self.gateway_cfg.get("gatewayId")
        return org_id, gw_id

    def _send_signal(self, group: str, results: Dict[str, Any]) -> None:
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

    def _build_signal_from_regs(
        self,
        regs: Dict[int, Optional[int]],
        modbus_dir: Dict[str, int],
    ) -> Dict[str, Optional[float]]:
        """
        Build signal using the address map and apply defined scales.
        """
        out: Dict[str, Optional[float]] = {}
        for name, addr in modbus_dir.items():
            raw = regs.get(addr)
            if raw is None:
                out[name] = None
                continue
            val = float(raw)
            scale = self.modbus_scales.get(name)
            out[name] = (val * scale) if scale else val
        return out
