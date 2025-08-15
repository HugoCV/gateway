# device_service.py
from typing import Dict, Any, Optional

from infrastructure.http.http_client import HttpClient
from infrastructure.logo.logo_client import LogoModbusClient
from infrastructure.modbus.modbus_tcp import ModbusTcp
from infrastructure.modbus.modbus_serial import ModbusSerial

class DeviceService:
    """
    Servicio por dispositivo que maneja sus propias conexiones a:
      - HTTP (HttpClient)
      - Modbus TCP (ModbusTcp)
      - Modbus Serial (ModbusSerial)
      - LOGO! (LogoModbusClient)
    y publica lecturas por MQTT usando el serial del dispositivo.
    """

    def __init__(
        self,
        *,
        mqtt_handler,                       
        gateway_cfg: Dict[str, Any],        
        device: Dict[str, Any],            
        log,                               
        signal_modbus_tcp_dir: Dict[str, int],
        signal_modbus_serial_dir: Dict[str, int],
        signal_logo_dir: Dict[str, int],
        modbus_scales: Dict[str, float],
        modbus_labels: Dict[str, str],
        logo_labels: Dict[str, str],
        http_interval: float = 5.0,
        poll_interval: float = 0.5,
    ) -> None:
        self.mqtt = mqtt_handler
        self.gateway_cfg = gateway_cfg
        self.device = device or {}
        self.log = log

        self.signal_modbus_tcp_dir = signal_modbus_tcp_dir
        self.signal_modbus_serial_dir = signal_modbus_serial_dir
        self.signal_logo_dir = signal_logo_dir
        self.modbus_scales = modbus_scales
        self.modbus_labels = modbus_labels
        self.logo_labels = logo_labels

        self.http_interval = http_interval
        self.poll_interval = poll_interval

        # Identidad del dispositivo
        self.device_id: str = (
            self.device.get("_id")
            or self.device.get("serialNumber")
            or self.device.get("name")
            or ""
        )
        self.serial: str = self.device.get("serialNumber", "")
        self.cc: Dict[str, Any] = self.device.get("connectionConfig") or {}

        # Handlers por dispositivo (se crean en start() si hay config)
        self.http: Optional[HttpClient] = None
        self.modbus_tcp: Optional[ModbusTcp] = None
        self.modbus_serial: Optional[ModbusSerial] = None
        self.logo: Optional[LogoModbusClient] = None

        # Polling threads/handlers devueltos por poll_registers (si aplica)
        self.tcp_poll = None
        self.serial_poll = None

        self.alive: bool = False

    # ---------------------------
    # Ciclo de vida
    # ---------------------------
    def start(self) -> None:
        """Crea conexiones por dispositivo según su connectionConfig."""
        if not self.device_id:
            self.log("⚠️ DeviceService: dispositivo sin identificador.")
            return

        org_id, gw_id = self._ids()
        if not org_id or not gw_id:
            self.log("⚠️ DeviceService: faltan organizationId/gatewayId.")
            return

        self.alive = True
        self.log(f"▶️ Iniciando DeviceService para {self.device_id}")

        # HTTP (opcional)
        if self.cc.get("host") and self.cc.get("httpPort"):
            try:
                base_url = f"http://{self.cc['host']}:{self.cc['httpPort']}/api/dashboard"
                # Firma usada en tu código: HttpClient(owner, on_read_cb, log_cb)
                self.http = HttpClient(self, self._on_http_read, self.log)
                self.http.connect(base_url=base_url, interval=self.http_interval)
                self.http.start_continuous_read()
                self.log(f"🌐 HTTP conectado: {base_url} ({self.device_id})")
            except Exception as e:
                self.log(f"⚠️ HTTP error ({self.device_id}): {e}")

        # Modbus TCP (opcional)
        # if self.cc.get("host") and self.cc.get("tcpPort"):
        #     try:
        #         # Firma usada en tu código: ModbusTcp(owner, on_read_cb, log_cb)
        #         self.modbus_tcp = ModbusTcp(self, self._on_modbus_tcp_read, self.log)
        #         self.modbus_tcp.connect(self.cc["host"], self.cc["tcpPort"])
        #         # En tu app lo dejas en local por defecto
        #         self.modbus_tcp.set_local()
        #         addrs = list(dict.fromkeys(self.signal_modbus_tcp_dir.values()))
        #         self.tcp_poll = self.modbus_tcp.poll_registers(
        #             addresses=addrs, interval=self.poll_interval
        #         )
        #         self.log(f"🔌 Modbus TCP conectado: {self.cc['host']}:{self.cc['tcpPort']} ({self.device_id})")
        #     except Exception as e:
        #         self.log(f"⚠️ Modbus TCP error ({self.device_id}): {e}")

        # # Modbus Serial (opcional, por dispositivo si cada uno tiene su puerto)
        # if self.cc.get("serialPort") and self.cc.get("baudrate") and self.cc.get("slaveId") is not None:
        #     try:
        #         # Firma usada en tu código: ModbusSerial(owner, on_read_cb, log_cb)
        #         self.modbus_serial = ModbusSerial(self, self._on_modbus_serial_read, self.log)
        #         self.modbus_serial.connect(
        #             port=self.cc["serialPort"],
        #             baudrate=self.cc["baudrate"],
        #             slave_id=self.cc["slaveId"],
        #         )
        #         addrs = list(dict.fromkeys(self.signal_modbus_serial_dir.values()))
        #         self.serial_poll = self.modbus_serial.poll_registers(
        #             addresses=addrs, interval=self.poll_interval
        #         )
        #         self.log(f"🧵 Modbus Serial conectado: {self.cc['serialPort']}@{self.cc['baudrate']} (sid={self.cc['slaveId']}) ({self.device_id})")
        #     except Exception as e:
        #         self.log(f"⚠️ Modbus Serial error ({self.device_id}): {e}")

        # # LOGO! (opcional)
        # if self.cc.get("logoIp") and self.cc.get("logoPort"):
        #     try:
        #         # Firma usada en tu código: LogoModbusClient(owner, log_cb, on_read_cb)
        #         self.logo = LogoModbusClient(self, self.log, self._on_logo_read)
        #         self.logo.connect(host=self.cc["logoIp"], port=self.cc["logoPort"])
        #         addrs = list(dict.fromkeys(self.signal_logo_dir.values()))
        #         self.logo.poll_registers(addrs)
        #         self.log(f"🧱 LOGO conectado: {self.cc['logoIp']}:{self.cc['logoPort']} ({self.device_id})")
        #     except Exception as e:
        #         self.log(f"⚠️ LOGO error ({self.device_id}): {e}")

        # if not any([self.http, self.modbus_tcp, self.modbus_serial, self.logo]):
        #     self.log(f"⚠️ {self.device_id} no tiene endpoints (HTTP/TCP/Serial/LOGO) configurados.")

    def stop(self) -> None:
        """Best-effort para detener conexiones del dispositivo."""
        self.alive = False
        self.log(f"⏹️ Deteniendo DeviceService para {self.device_id}")

        # Detener Modbus TCP
        if self.modbus_tcp and hasattr(self.modbus_tcp, "stop"):
            try:
                self.modbus_tcp.stop()
            except Exception:
                pass

        # Detener Modbus Serial (si tu clase tiene stop)
        if self.modbus_serial and hasattr(self.modbus_serial, "stop"):
            try:
                self.modbus_serial.stop()
            except Exception:
                pass

        # Detener HTTP si tu cliente tiene .stop()
        if self.http and hasattr(self.http, "stop"):
            try:
                self.http.stop()
            except Exception:
                pass

        # Detener LOGO si expone .stop()
        if self.logo and hasattr(self.logo, "stop"):
            try:
                self.logo.stop()
            except Exception:
                pass

        self.tcp_poll = None
        self.serial_poll = None

    # ---------------------------
    # Callbacks de lectura
    # ---------------------------
    def _on_http_read(self, results: Dict[str, Any]) -> None:
        # Publica lecturas HTTP como grupo 'drive'
        self._send_signal("drive", results)

    def _on_modbus_tcp_read(self, regs: Dict[int, int]) -> None:
        signal = self._build_signal_from_regs(regs, self.signal_modbus_tcp_dir)
        # Logs opcionales por etiqueta
        for k, label in self.modbus_labels.items():
            v = signal.get(k, None)
            if v is not None:
                self.log(f"ℹ️ [{self.device_id}] {label}: {v}")
        self._send_signal("drive", signal)

    def _on_modbus_serial_read(self, regs: Dict[int, int]) -> None:
        signal = self._build_signal_from_regs(regs, self.signal_modbus_serial_dir)
        for k, label in self.modbus_labels.items():
            v = signal.get(k, None)
            if v is not None:
                self.log(f"ℹ️ [{self.device_id}] {label}: {v}")
        self._send_signal("drive", signal)

    def _on_logo_read(self, regs: Dict[int, int]) -> None:
        signal = {name: regs.get(addr) for name, addr in self.signal_logo_dir.items()}
        for k, label in self.logo_labels.items():
            v = signal.get(k, None)
            if v is not None:
                self.log(f"ℹ️ [{self.device_id}] {label}: {v}")
        self._send_signal("logo", signal)

    # ---------------------------
    # Helpers internos
    # ---------------------------
    def _ids(self):
        org_id = self.gateway_cfg.get("organization_id") or self.gateway_cfg.get("organizationId")
        gw_id  = self.gateway_cfg.get("gateway_id") or self.gateway_cfg.get("gatewayId")
        return org_id, gw_id

    def _send_signal(self, group: str, results: Dict[str, Any]) -> None:
        """Publica por MQTT con el serial del dispositivo."""
        try:
            if not isinstance(results, dict) or not results:
                self.log("⚠️ Resultado vacío; no se envía MQTT.")
                return
            org_id, gw_id = self._ids()
            if not org_id or not gw_id:
                self.log(f"⚠️ Faltan IDs en gateway_cfg: org={org_id} gw={gw_id}")
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
        Construye señal usando el mapa de direcciones y aplica escalas definidas.
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
