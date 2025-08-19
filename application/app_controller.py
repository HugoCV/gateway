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
            self.on_send_signal,
            self.window._log
        )
        self.modbus_serial_handler = ModbusSerial(
            self,
            self.on_send_signal,
            self.window._log,
        )
        self.logo_handler = LogoModbusClient(
            self,
            self.on_send_signal,
            self.window._log
        )
        self.http_handler = HttpClient(
            self,
            self.on_send_signal,
            self.window._log,
        )
        self.mqtt_handler = MqttClient(
            self.gateway_cfg,
            self.on_initial_load,
            log_callback=self.window._log,
            command_callback=self.on_receive_command
        )

        # Usar constantes globales
        self.signal_modbus_tcp_dir = SIGNAL_MODBUS_TCP_DIR
        self.signal_modbus_serial_dir = SIGNAL_MODBUS_SERIAL_DIR
        self.signal_logo_dir = SIGNAL_LOGO_DIR

        # Conectar MQTT al final
        self.on_connect_mqtt()

        self.device_manager = DeviceManager(self.mqtt_handler, self.refresh_device_list, self.window._log)
        self.gateway_manager = GatewayManager(self.mqtt_handler, self._refresh_gateway_fields, self.window._log)
        self.devices = []


    # === commands ===
    def on_receive_command(self, device_serial, command):
        if not self.devices:
            self.window._log(f"no hay dispositivos conectados commando recivido {command}")
        match command["action"]:
            case "update-status":
                # self.device_services[device_serial]
                print("update-status :", command["params"]["value"], "device_serial", device_serial )
            case "update-connections":
                self.devices[device_serial].update_connection_config(command["params"])
            case "update-config":
                print("update-config", command["params"]["value"], "device_serial", device_serial)
        
        
        # self.window._log(f"[CMD] device={device_id} -> {command}")

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
        self.mqtt_handler.on_send_signal(results, group)

    # === Devices ===
    def get_device_by_name(self, name):
        return next((d for d in self.device_manager.devices if d.get("name") == name), None)

    def refresh_device_list(self, devices=None) -> None:
        if devices is None:
            devices = {}

        self.devices = self.create_all_devices(devices)
        self.services = list(self.devices.values())
        names = [svc.device["name"] for svc in self.services]
        self.window.device_combo["values"] = names
        if names:
            self.window.device_combo.current(0)
            self.update_device_fields(self.services[0])
        else:
            self.window.device_combo.set("")
            self.update_device_fields({})

    def create_all_devices(self, devices):
        device_services = {}
        for dev in devices:
            ds = DeviceService(
                mqtt_handler=self.mqtt_handler,
                gateway_cfg=self.gateway_cfg,
                device=dev,
                log=self.window._log,
                update_fields=self.update_device_fields
            )
            device_services[ds.serial] = ds
        return device_services

    def on_select_device(self, event=None):
        selected = self.window.selected_device_var.get()
        device = self.get_device_by_name(selected)
        if not device:
            self.window._log("Dispositivo no encontrado.")
            return
        self.update_device_fields(device)

    def update_device_fields(self, device_service) -> None:
        """
        Populate UI fields from either:
        - a plain dict with a 'connectionConfig' key, or
        - a DeviceService-like instance (has .device and .cc attributes).

        Prefers the DeviceService attributes when present:
        name  -> service.device["name"] (fallback: service.device_id)
        model -> service.model or service.device["deviceModel"]
        serial-> service.serial or service.device["serialNumber"]
        cc    -> service.cc
        """
        # Detect "service-like" object via duck typing to avoid imports/cycles
        is_service_like = hasattr(device_service, "cc") or hasattr(device_service, "device")

        if is_service_like:
            svc = device_service
            d = getattr(svc, "device", {}) or {}
            cc = getattr(svc, "cc", {}) or {}

            name   = d.get("name") or getattr(svc, "device_id", "")
            model  = getattr(svc, "model", "") or d.get("deviceModel", "")
            serial = getattr(svc, "serial", "") or d.get("serialNumber", "")
        else:
            
            d = device_service or {}
            cc = d.get("connectionConfig") or {}

            name   = d.get("name", "")
            model  = d.get("deviceModel", "")
            serial = d.get("serialNumber", "")
        self.selected_serial = serial
        # Small helper: always set a string; empty string for None
        def set_str(var, value):
            var.set("" if value is None else str(value))

        # Top-level device fields
        set_str(self.window.device_name_var, name)
        set_str(self.window.serial_var,      serial)
        set_str(self.window.model_var,       model)

        # Connection config fields (HTTP / TCP share 'host' unless you split them)
        set_str(self.window.http_ip_var,     cc.get("host", ""))
        set_str(self.window.http_port_var,   cc.get("httpPort", ""))
        set_str(self.window.tcp_ip_var,      cc.get("host", ""))
        set_str(self.window.tcp_port_var,    cc.get("tcpPort", ""))

        # Serial / LOGO fields
        set_str(self.window.serial_port_var, cc.get("serialPort", ""))
        set_str(self.window.baudrate_var,    cc.get("baudrate", ""))
        set_str(self.window.slave_id_var,    cc.get("slaveId", ""))
        set_str(self.window.logo_ip_var,     cc.get("logoIp", ""))
        set_str(self.window.logo_port_var,   cc.get("logoPort", ""))

    # === HTTP Client ===
    def on_connect_http(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        svc.connect_http()

    def on_http_read_callback(self, results: dict) -> None:
        # Vuelve al hilo de Tkinter
        self.on_send_signal(results, "drive")
        # self.window.after(0, lambda: self.on_send_signal(results, "drive"))

    def on_http_read_fault(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        svc.read_http_fault()


    # === Modbus Serial ===
    def on_connect_modbus_serial_old(self):
        self.window._log("tratando de conectar a travez de modbus serial")
        self.modbus_serial_handler.connect(
            port=self.window.serial_port_var.get(),
            baudrate=self.window.baudrate_var.get(),
            slave_id=self.window.slave_id_var.get(),
        )

    def on_connect_modbus_serial(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        self.window._log("tratando de conectar a travez de modbus serial")
        svc._stop_modbus_serial()
        svc.start_modbus_serial()
    def on_set_remote_serial(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        #self.modbus_serial_handler.write_register(4357,  3, device_id=1)
        self.modbus_serial_handler.write_register(address=4358, value=3, slave=1)

    def on_start_modbus_serial(self):
        self.modbus_serial_handler.write_register(897, self.window.slave_id_var.get(), 3)

    def on_stop_modbus_serial(self):
        self.modbus_serial_handler.write_register(897, self.window.slave_id_var.get(), 0)

    def on_reset_modbus_serial(self):
        self.modbus_serial_handler.write_register(900, self.window.slave_id_var.get(), 1)
        self.modbus_serial_handler.write_register(900, self.window.slave_id_var.get(), 0)
        self.modbus_serial_handler.write_register(897, self.window.slave_id_var.get(), 2)

    def on_multiple_modbus_serial(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        svc.multiple_modbus_serial_read()

    # === Modbus TCP ===
    def on_connect_modbus_tcp(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        svc.connect_modbus_tcp()

    def on_start_modbus_tcp(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        svc.connect_modbus_tcp()

    def on_stop_modbus_tcp(self):
        self.modbus_tcp_handler.stop()

    def on_reset_modbus_tcp(self):
        self.modbus_tcp_handler.set_remote()

    def on_custom_modbus_tcp(self):
        self.modbus_tcp_handler.set_local()

    def on_start_modbus_tcp(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        svc.connect_http()

    def on_set_remote_tcp(self):
        self.modbus_tcp_handler.write_register(address=4358, value=2)

    # === Logo ===
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
