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
        self.log = window._log
        self.gateway_cfg = get_gateway()
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
                if not (svc := self.devices.get(device_serial)):
                    self.window._log("⚠️ No device selected.")
                    return
                if(command["params"]["value"] == "on"):
                    self.log(f"El dispositivo {svc.name} se mando a encender")
                    svc.turn_on()
                else:
                    self.log(f"El dispositivo {svc.name} se mando a apagar")
                    svc.turn_off()

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
            self.selected_serial = self.services[0].serial
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
        deviceDir = self.get_device_by_name(selected)
        device = self.devices.get(deviceDir["serialNumber"])
        self.selected_serial = device.serial
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
        
        if(self.selected_serial != device_service.serial):
            return 
            
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

    def on_http_read_fault(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        svc.read_http_fault()


    # === Modbus Serial ===
    def on_connect_modbus_serial(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        self.window._log("tratando de conectar a travez de modbus serial")
        svc.disconnect_modbus_serial()
        svc.connect_modbus_serial()

    def on_turn_on_modbus_serial(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        self.window._log("ratando de encener a travez de modbus serial")
        svc.turn_on_modbus_serial()
        # self.modbus_serial_handler.write_register(897, self.window.slave_id_var.get(), 3)

    def on_turn_off_modbus_serial(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        self.window._log("ratando de apagar a travez de modbus serial")
        svc.turn_off_modbus_serial()

    def on_restart_modbus_serial(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        self.window._log("ratando de apagar a travez de modbus serial")
        svc.restart_modbus_seial()

    def on_multiple_modbus_serial(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        svc.start_reading_modbus_serial()

    # === Modbus TCP ===
    def on_connect_modbus_tcp(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        svc.connect_modbus_tcp()
        

    def on_turn_on_modbus_tcp(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        svc.turn_on_modbus_tcp()

    def on_turn_off_modbus_tcp(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        svc.turn_off_modbus_tcp()

    def on_reset_modbus_tcp(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        svc.turn_off_modbus_tcp()

    def on_read_modbus_tcp(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        svc.start_reading_modbus_tcp()

    # === Logo ===
    def on_read_logo(self):
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        svc.start_reading_logo

    def on_connect_logo(self):
        """Conecta a dispositivo Logo via TCP."""
        if not (svc := self.devices.get(self.selected_serial)):
            self.window._log("⚠️ No device selected.")
            return
        svc.connect_logo()

    def on_turn_off_logo(self):
        succeded = self.logo_handler.write_coil(4, 1)
        if succeded:
            return self.window._log("Se apago desde el logo")
        self.window._log("Error al apagar desde el logo")

    def on_turn_on_logo(self):
        succeded = self.logo_handler.write_coil(3, 1)
        if succeded:
            return self.window._log("Se encendio desde el logo")
        self.window._log("Error al encender desde el logo")

    def on_reset_logo(self):
        self.window._log("🔁 Logo: Reset presionado.")
