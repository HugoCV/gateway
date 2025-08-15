from application.managers.gateway_manager import GatewayManager
from application.managers.device_manager import DeviceManager
from application.services.device_service import DeviceService
from infrastructure.http.http_client import HttpClient
from infrastructure.logo.logo_client import LogoModbusClient
from infrastructure.modbus.modbus_serial import ModbusSerial
from infrastructure.modbus.modbus_tcp import ModbusTcp
from infrastructure.mqtt.mqtt_client import MqttClient
from infrastructure.config.loader import get_gateway

# =========================
# Constantes globales
# =========================

MODBUS_LABELS = {
    "freqRef": "Referencia de frecuencia",
    "accTime": "Tiempo de aceleración",
    "decTime": "Tiempo de desaceleración",
    "curr":    "Amperaje de salida",
    "freq":    "Frecuencia de salida",
    "volt":    "Voltaje de salida",
    "voltDcLink": "Voltaje DC Link",
    "power":   "Potencia en kW",
    "stat":    "Estado",
    "dir":     "Dirección",
    "speed":   "Velocidad (rpm)",
    "alarm":   "Alarma",
    "temp":    "Temperatura",
    "fault":   "Falla",
}

LOGO_LABELS = {
    "faultRec": "Voltage fault recovery time",
    "faultRes": "Fault reset time",
    "workHours": "Working hours",
    "workMinutes": "Working minutes",
    "faultLowWater": "Tank Low Water Level Fault",
    "highPressureRes": "High-pressure reset delay",
}

# Escalas por clave (aplican si la clave existe y el valor no es None)
MODBUS_SCALES = {
    "curr": 0.1,      # /10
    "power": 0.1,     # /10
    "freqRef": 0.01,  # /100
    "freq": 0.01,     # /100
}

SIGNAL_MODBUS_TCP_DIR = {
    "freqRef": 5,
    "accTime": 7,
    "decTime": 8,
    "curr": 9,
    "freq": 10,
    "volt": 11,
    "voltDcLink": 12,
    "power": 13,       # si no se puede saber, devuelves None si no existe
    "fault": 15,
    "stat": 17,        # 0=stop 1=falla 2=operacion
    "dir": 19,         # ajusta si cambia
    "speed": 786,
    "alarm": 816,
    "temp": 861,
}

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

SIGNAL_LOGO_DIR = {
    "faultRec": 2,
    "faultRes": 4,
    "workHours": 5,
    "workMinutes": 6,
    "faultLowWater": 8,
    "highPressureRes": 11,
}


class AppController:
    """
    Controlador principal de la aplicación Tkinter.
    Gestiona conexiones MQTT, Modbus (TCP/Serial), Logo y HTTP.
    """

    def __init__(self, window):
        self.window = window
        self.gateway_cfg = get_gateway()

        

        # Handlers
        self.modbus_tcp_handler = ModbusTcp(
            self,
            self.on_modbus_tcp_read_callback,
            self.window._log
        )
        self.modbus_serial_handler = ModbusSerial(
            self,
            self.on_modbus_serial_read_callback,
            self.window._log,
        )
        self.logo_handler = LogoModbusClient(
            self,
            self.window._log,
            self.on_logo_read_callback
        )
        self.http_handler = HttpClient(
            self,
            self.on_http_read_callback,
            self.window._log,
        )

        self.mqtt_handler = MqttClient(
            self.gateway_cfg,
            self.on_initial_load,
            log_callback=self.window._log,
            command_callback=self.on_receive_command
        )

        self.devices = []
        self.selected_device_handler = None

        # Usar constantes globales
        self.signal_modbus_tcp_dir = SIGNAL_MODBUS_TCP_DIR
        self.signal_modbus_serial_dir = SIGNAL_MODBUS_SERIAL_DIR
        self.signal_logo_dir = SIGNAL_LOGO_DIR

        # Conectar MQTT al final
        self.on_connect_mqtt()

        self.device_manager = DeviceManager(self.mqtt_handler, self.refresh_device_list, self.window._log)
        self.gateway_manager = GatewayManager(self.mqtt_handler, self._refresh_gateway_fields, self.window._log)

    # === commands ===
    def on_receive_command(self, device_id, command):
        self.window._log(f"[CMD] device={device_id} -> {command}")

    # === initial load ===
    def on_initial_load(self):
        self.gateway_manager.load_gateway()
        self.device_manager.load_devices()

    # === Gateway ===
    def _refresh_gateway_fields(self, gateway):
        # Usar variables del window
        self.window.gw_name_var.set(gateway.get("name", ""))
        self.window.loc_var.set(gateway.get("location", ""))

    # === MQTT ===
    def on_connect_mqtt(self):
        self.mqtt_handler.connect()

    def on_send_signal(self, results, group):
        """
        results: dict con lecturas
        group:   'drive' | 'logo' | etc.
        """
        try:
            if not isinstance(results, dict) or not results:
                self.window._log("⚠️ Resultado vacío o no es dict; no se envía MQTT.")
                return

            serial = (self.window.serial_var.get() or "").strip()
            if not serial:
                self.window._log("⚠️ Serial vacío; se omite envío MQTT.")
                return

            # Acepta organization_id/organizationId y gateway_id/gatewayId
            org_id = self.gateway_cfg.get("organization_id") or self.gateway_cfg.get("organizationId")
            gw_id  = self.gateway_cfg.get("gateway_id") or self.gateway_cfg.get("gatewayId")
            if not org_id or not gw_id:
                self.window._log(f"⚠️ Faltan IDs en gateway_cfg: org={org_id} gw={gw_id}")
                return

            topic_info = {
                "serial_number":  serial,
                "organization_id": org_id,
                "gateway_id":      gw_id,
            }
            signal = {"group": group, "payload": results}
            self.mqtt_handler.send_signal(topic_info, signal)
        except Exception as e:
            # mensaje correcto para esta función
            self.window._log(f"❌ on_send_signal error: {e}")

    # === Devices ===
    def get_device_by_name(self, name):
        return next((d for d in self.device_manager.devices if d.get("name") == name), None)

    def refresh_device_list(self, devices=[]):
        self.start_all(devices)
        self.devices = devices or []
        names = [d.get("name", "") for d in self.devices]
        self.window.device_combo["values"] = names
        if names:
            self.window.device_combo.current(0)
            self.update_device_fields(self.devices[0])

    def start_all(self, devices):
        self.device_services = {}
        for dev in devices:
            ds = DeviceService(
                mqtt_handler=self.mqtt_handler,
                gateway_cfg=self.gateway_cfg,
                device=dev,
                log=self.window._log,
                signal_modbus_tcp_dir=SIGNAL_MODBUS_TCP_DIR,
                signal_modbus_serial_dir=SIGNAL_MODBUS_SERIAL_DIR,
                signal_logo_dir=SIGNAL_LOGO_DIR,
                modbus_scales=MODBUS_SCALES,
                modbus_labels=MODBUS_LABELS,
                logo_labels=LOGO_LABELS,
            )
            ds.start()
            self.device_services[ds.device_id] = ds

    def on_select_device(self, event=None):
        selected = self.window.selected_device_var.get()
        device = self.get_device_by_name(selected)
        if not device:
            self.window._log("Dispositivo no encontrado.")
            return
        self.update_device_fields(device)

    def update_device_fields(self, device):
        cc = device.get("connectionConfig") or {}
        self.window.device_name_var.set(device.get("name", ""))
        self.window.serial_var.set(device.get("serialNumber", ""))
        self.window.model_var.set(device.get("deviceModel", ""))

        self.window.http_ip_var.set(cc.get("host", ""))
        self.window.http_port_var.set(cc.get("httpPort", ""))
        self.window.serial_port_var.set(cc.get("serialPort", ""))
        self.window.baudrate_var.set(cc.get("baudrate", ""))
        self.window.slave_id_var.set(cc.get("slaveId", ""))
        self.window.logo_ip_var.set(cc.get("logoIp", ""))
        self.window.logo_port_var.set(cc.get("logoPort", ""))
        self.window.tcp_ip_var.set(cc.get("host", ""))
        self.window.tcp_port_var.set(cc.get("tcpPort", ""))

    # === HTTP Client ===
    def on_connect_http(self):
        ip = self.window.http_ip_var.get()
        port = self.window.http_port_var.get()
        if ip and port:
            base_url = f"http://{ip}:{port}/api/dashboard"
            self.http_handler.connect(base_url=base_url, interval=5)
            self.http_handler.start_continuous_read()
            self.window._log(f"🌐 HTTPClient conectado a: {base_url}")
        else:
            self.window._log("⚠️ IP o puerto HTTP no definidos.")

    def on_http_read_callback(self, results: dict) -> None:
        # Vuelve al hilo de Tkinter
        self.window.after(0, lambda: self.on_send_signal(results, "drive"))

    def on_multiple_http(self):
        fault_history = self.http_handler.read_fault_history_sync()
        if fault_history:
            self.window._log(f"Historial recibido: {fault_history}")
        else:
            self.window._log("No se pudo obtener el historial.")

    # === Utilidad: construir señal con escalas conocidas ===
    def _build_signal_from_regs(self, regs: dict[int, int], modbus_dir) -> dict:
        """
        Crea dict de señal a partir de registros, aplicando escalas definidas en MODBUS_SCALES.
        """
        s = {}
        for name, addr in modbus_dir.items():
            v = regs.get(addr)
            if v is None:
                s[name] = None
                continue
            if name in MODBUS_SCALES:
                s[name] = v * MODBUS_SCALES[name]
            else:
                s[name] = v
        return s

    # === Modbus Serial ===
    def on_connect_modbus_serial(self):
        self.window._log("tratando de conectar a travez de modbus serial")
        self.modbus_serial_handler.connect(
            port=self.window.serial_port_var.get(),
            baudrate=self.window.baudrate_var.get(),
            slave_id=self.window.slave_id_var.get(),
        )
        self.selected_device_handler = self.modbus_serial_handler

    def on_set_remote_serial(self):
        self.modbus_serial_handler.write_register(address=4358, value=2)

    def on_start_modbus_serial(self):
        self.modbus_serial_handler.write_register(897, self.window.slave_id_var.get(), 3)

    def on_stop_modbus_serial(self):
        self.modbus_serial_handler.write_register(897, self.window.slave_id_var.get(), 0)

    def on_reset_modbus_serial(self):
        self.modbus_serial_handler.write_register(900, self.window.slave_id_var.get(), 1)
        self.modbus_serial_handler.write_register(900, self.window.slave_id_var.get(), 0)
        self.modbus_serial_handler.write_register(897, self.window.slave_id_var.get(), 2)

    def on_multiple_modbus_serial(self):
        addresses = list(dict.fromkeys(self.signal_modbus_serial_dir.values()))
        self.window._log(f"[Serial] Polling: {addresses}")
        self.modbus_serial_thread = self.modbus_serial_handler.poll_registers(
            addresses=addresses,
            interval=0.5,
        )

    def on_modbus_serial_read_callback(self, regs):
        signal = self._build_signal_from_regs(regs, self.signal_modbus_serial_dir)
        for k, label in MODBUS_LABELS.items():
            v = signal.get(k, None)
            if v is not None:
                self.window._log(f"ℹ️ {label}: {v}")
        # Publicación opcional por MQTT
        self.on_send_signal(signal, "drive")

    # === Modbus TCP ===
    def on_connect_modbus_tcp(self):
        """Inicia cliente Modbus TCP y lo deja en modo local."""
        ip = (self.window.tcp_ip_var.get() or "").strip()
        port = self.window.tcp_port_var.get()
        if not ip or not port:
            self.window._log("⚠️ IP o puerto no definidos.")
            return

        self.modbus_tcp_handler.connect(ip, port)
        self.modbus_tcp_handler.set_local()
        self.selected_device_handler = self.modbus_tcp_handler

    def on_start_modbus_tcp(self):
        self.modbus_tcp_handler.start()

    def on_stop_modbus_tcp(self):
        self.modbus_tcp_handler.stop()

    def on_reset_modbus_tcp(self):
        self.modbus_tcp_handler.set_remote()

    def on_custom_modbus_tcp(self):
        self.modbus_tcp_handler.set_local()

    def on_multiple_modbus_tcp(self):
        addresses = list(dict.fromkeys(self.signal_modbus_tcp_dir.values()))
        self.window._log(f"[TCP] Polling: {addresses}")
        # reusar el mismo atributo si así lo tenías
        self.modbus_serial_thread = self.modbus_tcp_handler.poll_registers(
            addresses=addresses,
            interval=0.5,
        )

    def on_set_remote_tcp(self):
        self.modbus_tcp_handler.write_register(address=4358, value=2)

    def on_modbus_tcp_read_callback(self, regs):
        signal = self._build_signal_from_regs(regs, self.signal_modbus_tcp_dir)
        for k, label in MODBUS_LABELS.items():
            v = signal.get(k, None)
            if v is not None:
                self.window._log(f"ℹ️ {label}: {v}")
        self.on_send_signal(signal, "drive")

    # === Logo ===
    def _build_logo_signal_from_regs(self, regs: dict[int, int]) -> dict:
        return {name: regs.get(addr) for name, addr in self.signal_logo_dir.items()}

    def on_logo_read_callback(self, regs):
        signal = self._build_logo_signal_from_regs(regs)
        for k, label in LOGO_LABELS.items():
            v = signal.get(k, None)
            if v is not None:
                self.window._log(f"ℹ️ {label}: {v}")
        # Publicación opcional por MQTT (grupo 'logo')
        self.on_send_signal(signal, "logo")

    def on_multiple_logo(self):
        addresses = list(dict.fromkeys(self.signal_logo_dir.values()))
        self.window._log(f"[LOGO] Polling: {addresses}")
        self.logo_handler.poll_registers(addresses)

    def on_connect_logo(self):
        """Conecta a dispositivo Logo via TCP."""
        self.logo_handler.connect(
            host=self.window.logo_ip_var.get(),
            port=self.window.logo_port_var.get(),
        )
        self.selected_device_handler = self.logo_handler

    def on_write_logo(self):
        self.logo_handler.write_single_register(1, 10)

    def on_read_logo(self):
        address = 6
        succeded = self.logo_handler.read_registers(address, 1)
        if succeded:
            return self.window._log(f"se leyo en la direccion {address}")
        self.window._log("Error al leer desde el LOGO")

    def on_stop_logo(self):
        succeded = self.logo_handler.write_coil(4, 1)
        if succeded:
            return self.window._log("Se apago desde el logo")
        self.window._log("Error al apagar desde el logo")

    def on_start_logo(self):
        succeded = self.logo_handler.write_coil(3, 1)
        if succeded:
            return self.window._log("Se encendio desde el logo")
        self.window._log("Error al encender desde el logo")

    def on_reset_logo(self):
        self.window._log("🔁 Logo: Reset presionado.")
