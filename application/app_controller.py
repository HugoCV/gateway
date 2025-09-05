import os, sys, time
import threading
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
# Global
# =========================


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
            command_callback=self.on_receive_command,
            command_gateway_callback=self.on_receive_gateway_command
        )

        # Conectar MQTT al final
        self.on_connect_mqtt()

        self.device_manager = DeviceManager(self.mqtt_handler, self.refresh_device_list, self.window._log)
        self.gateway_manager = GatewayManager(self.mqtt_handler, self._refresh_gateway_fields, self.window._log)
        self.devices = {}

        self.monitor_threads()




    def monitor_threads(self, interval: float = 2.0):
        """Start a background thread that logs active thread count periodically."""
    
        def _worker():
            while True:
                threads = threading.enumerate()
                print("threads", len(threads))
                time.sleep(interval)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t
    # === commands ===
    def on_receive_gateway_command(self, command):
        print("on_receive_gateway_command", command)
        
        match command["action"]:
            case "restart":
                os.execv(sys.executable, [sys.executable] + sys.argv)
            case "restart-gateway":
                print("restart")

    
    def on_receive_command(self, device_serial, command):
        if not self.devices:
            self.window._log(f"no hay dispositivos conectados commando recivido {command}")
        if not (ds := self.devices.get(device_serial)):
                    self.window._log("⚠️ No device selected.")
                    return    
        match command["action"]:
            case "update-connections":
                    ds.update_connection_config(command["params"])
            case "update-status":
                value = str(command.get("params", {}).get("value", "")).lower()
                if value == "on":
                    self.log(f"El dispositivo {ds.name} se mandó a encender")
                    ds.turn_on()
                elif value == "off":
                    self.log(f"El dispositivo {ds.name} se mandó a apagar")
                    ds.turn_off()
                elif value == "restart":
                    self.log(f"El dispositivo {ds.name} se mandó a reiniciar")
                    ds.restart()
            case "update-config":
                print("update-config", command["params"]["value"], "device_serial", device_serial)
        
    # === initial load ===
    def on_initial_load(self):
        self.gateway_manager.load_gateway()
        self.device_manager.load_devices()

    # === Gateway ===
    def _refresh_gateway_fields(self, gateway):
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
        for ds in getattr(self, "devices", {}).values():
            ds.stop()

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
