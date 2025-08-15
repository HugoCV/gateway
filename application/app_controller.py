from tkinter import messagebox
from application.managers.gateway_manager import GatewayManager
from application.managers.device_manager import DeviceManager
from infrastructure.http.http_client import HttpClient
from infrastructure.logo.logo_client import LogoModbusClient
from infrastructure.modbus.modbus_serial import ModbusSerial
from infrastructure.modbus.modbus_tcp import ModbusTcp
from infrastructure.mqtt.mqtt_client import MqttClient
from infrastructure.config.loader import get_gateway


class AppController:
    """
    Controlador principal de la aplicación Tkinter.
    Gestiona conexiones MQTT, Modbus (TCP/Serial), Logo y HTTP.
    """

    def __init__(self, window):
        self.window = window
        self.gateway_cfg = get_gateway()
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
        self.devices = []


        self.signal_modbus_tcp_dir = {
            "freqRef": 5, # Esta bien
            "accTime": 7, # Esta bien
            "decTime": 8, # Esta bien
            "curr":    9, # Esta bien
            "freq":    10, # Esta bien
            "volt":    11, # Esta bien
            "voltDcLink": 12, # Esta bien
            "power":   13,  # No se puede saber
            "stat":    17, #Esta bien 0=stop 1=falla 2=operacion
            "dir":     19,   # cámbialo si 'dir' es otro registro
            "speed":   786, #Esta bien
            "alarm":   816,
            "temp":    861,
            "fault":   15
        }
        
        self.signal_modbus_serial_dir = {
            "freqRef": 4,
            "accTime": 6,
            "decTime": 7,
            "curr":    8,
            "freq":    9,
            "volt":    10,
            "power":   12,   # ← como dijiste: power -> 12
            "stat":    16,
            "dir":     16,   # cámbialo si 'dir' es otro registro
            "speed":   785,
            "alarm":   815,
            "temp":    860,
        }

        self.signal_logo_dir = {
            "faultRec": 2, # Voltage fault recovery time
            "faultRes": 4, # Fault reset time
            "workHours": 5, # Working hours
            "workMinutes": 6, # Working minutes
            "faultLowWater": 8, # Tank Low Water Level Fault
            "highPressureRes": 11 # High-pressure reset delay
        }

        self.mqtt_handler = MqttClient(
            self.gateway_cfg,
            self.on_initial_load,
            log_callback=self.window._log,
            command_callback=self.on_receive_command
        )
        self.on_connect_mqtt()
        self.http_handler = HttpClient(
                self,
                self.on_http_read_callback,
                self.window._log,
            )
        
        self.selected_device_handler = None
        
        self.device_manager = DeviceManager(self.mqtt_handler, self.refresh_device_list, self.window._log)
        self.gateway_manager = GatewayManager(self.mqtt_handler, self._refresh_gateway_fields, self.window._log)
    # === commands ===
    def on_receive_command(self, device_id, command):
        print("command", device_id,command)
        


    # === initial load ===   

    def on_initial_load(self):
        self.gateway_manager.load_gateway()
        self.device_manager.load_devices()

    # === Gateway ===        

    def _refresh_gateway_fields(self, gateway):
        self.gw_name_var.set(gateway["name"])
        self.loc_var.set(gateway["location"])

    # === MQTT ===

    def on_connect_mqtt(self):
        self.mqtt_handler.connect()

    def on_send_signal(self, results, group):
        try:
            
            if not isinstance(results, dict) or not results:
                self.window._log("⚠️ Resultado vacío o no es dict; no se envía MQTT.")
                return
            serial = (self.window.serial_var.get() or "").strip()
            if not serial:
                self.window._log("⚠️ Serial vacío; se omite envío MQTT.")
                return

            topic_info = {
                "serial_number":  serial,
                "organization_id": self.gateway_cfg.get("organization_id") or self.gateway_cfg.get("organizationId"),
                "gateway_id":      self.gateway_cfg.get("gateway_id")      or self.gateway_cfg.get("gatewayId"),
            }

            if not topic_info["organization_id"] or not topic_info["gateway_id"]:
                self.window._log(f"⚠️ Faltan IDs en gateway_cfg: {topic_info}")
                return
            
            signal = {
                "group": group,
                "payload": results
            }
            
            self.mqtt_handler.send_signal(topic_info, signal)
        except Exception as e:
            self.window._log(f"❌ on_http_read_callback error: {e}")

    # === Devices ===

    def get_device_by_name(self, name):
        """Busca un dispositivo por nombre en la lista cargada."""
        return next((d for d in self.device_manager.devices if d.get("name") == name), None)

    def refresh_device_list(self, devices=[]):
        """Actualiza el combobox de dispositivos y selecciona el primero."""
        print(devices)
        names = [d.get("name") for d in devices]
        self.window.device_combo["values"] = names
        if names:
            self.window.device_combo.current(0)
            self.update_device_fields(devices[0])

    def on_select_device(self, event=None):
        """
        Evento al seleccionar un dispositivo.
        Configura HttpClient y actualiza campos de la UI.
        """
        selected = self.window.selected_device_var.get()
        device = self.get_device_by_name(selected)
        if not device:
            self.window._log("Dispositivo no encontrado.")
            return

        self.update_device_fields(device)

    def update_device_fields(self, device):
        """
        Rellena los campos de la interfaz según los datos del dispositivo.
        """
        self.window.device_name_var.set(device["name"])
        self.window.serial_var.set(device["serialNumber"])
        self.window.model_var.set(device["deviceModel"])
        self.window.http_ip_var.set(device["connectionConfig"]["host"])
        self.window.http_port_var.set(device["connectionConfig"]["httpPort"])
        self.window.serial_port_var.set(device["connectionConfig"]["serialPort"])
        self.window.baudrate_var.set(device["connectionConfig"]["baudrate"])
        self.window.slave_id_var.set(device["connectionConfig"]["slaveId"])
        self.window.logo_ip_var.set(device["connectionConfig"]["logoIp"])
        self.window.logo_port_var.set(device["connectionConfig"]["logoPort"])
        self.window.tcp_ip_var.set(device["connectionConfig"]["host"])
        self.window.tcp_port_var.set(device["connectionConfig"]["tcpPort"])

    # === HTTP Client ===

    def on_connect_http(self):
        """Evento placeholder para conexión HTTP."""
        ip = self.window.http_ip_var.get()
        port = self.window.http_port_var.get()
        if ip and port:
            base_url = f"http://{ip}:{port}/api/dashboard"
            self.http_handler.connect(base_url=base_url, interval=5)
            # fault_history = self.http_handler.read_fault_history_sync()
            # self._handle_http_results(fault_history[0], "history")
            self.http_handler.start_continuous_read()
            
            self.window._log(f"🌐 HTTPClient conectado a: {base_url}")
            
        else:
            self.window._log("⚠️ IP o puerto HTTP no definidos.")

    def on_http_read_callback(self, results: dict) -> None:
        """Callback invocado desde HttpClient (posible hilo/loop async)."""
        self.window.after(0, lambda: self.on_send_signal(results, "drive"))

    def on_multiple_http(self):
        """
        Llamada síncrona desde Tkinter que agenda la corrutina en el loop async
        y devuelve el resultado.
        """
        fault_history = self.http_handler.read_fault_history_sync()
        if fault_history:
            self.window._log(f"Historial recibido: {fault_history}")
        else:
            self.window._log("No se pudo obtener el historial.")

    # === Modbus Serial ===

    def on_connect_modbus_serial(self):
        """Conecta Modbus Serial con parámetros de la UI."""
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
        """Envía comando RUN por Modbus Serial."""
        self.modbus_serial_handler.write_register(897, self.window.slave_id_var.get(), 3)

    def on_stop_modbus_serial(self):
        """Envía comando STOP por Modbus Serial."""
        self.modbus_serial_handler.write_register(897, self.window.slave_id_var.get(), 0)

    def on_reset_modbus_serial(self):
        """Envía secuencia de reset por Modbus Serial."""
        self.modbus_serial_handler.write_register(900, self.window.slave_id_var.get(), 1)
        self.modbus_serial_handler.write_register(900, self.window.slave_id_var.get(), 0)
        self.modbus_serial_handler.write_register(897, self.window.slave_id_var.get(), 2)

    def on_multiple_modbus_serial(self):
        addresses = list(dict.fromkeys(self.signal_modbus_serial_dir.values()))
        print(addresses)
        self.modbus_serial_thread = self.modbus_serial_handler.poll_registers(
            addresses=addresses,
            interval=0.5,
        )

    def _build_signal_from_regs(self, regs: dict[int, int], modbus_dir) -> dict:
        s = {name: regs.get(addr) for name, addr in modbus_dir.items()}
        if s["curr"]  is not None: s["curr"]  /= 10
        if s["power"] is not None: s["power"] /= 10
        if s["freqRef"] is not None: s["freqRef"] /= 100
        if s["freq"] is not None: s["freq"] /= 100
        return s
    
    def on_modbus_serial_read_callback(self, regs):
        """Lee según signal_modbus_serial_dir, aplica escala y loguea."""
        print(regs)
        signal = self._build_signal_from_regs(regs, self.signal_modbus_serial_dir)

        labels = {
            "freqRef": "Referencia de frecuencia",
            "accTime": "Tiempo de aceleración",
            "decTime": "Tiempo de desaceleración",
            "curr":    "Amperaje de salida",
            "freq":    "Frecuencia de salida",
            "volt":    "Voltaje de salida",
            "power":   "Potencia en kW",
            "stat":    "Estado",
            "dir":     "Dirección",
        }
        for k, label in labels.items():
            v = signal.get(k, None)
            if v is not None:
                self.window._log(f"⚠️ {label}: {v}")

        print(signal)

    # === Modbus TCP ===

    def on_connect_modbus_tcp(self):
        """Inicia servidor Modbus TCP."""
        ip = self.window.tcp_ip_var.get().strip()
        port = self.window.tcp_port_var.get()
        if not ip or not port:
            self.window._log("⚠️ IP o puerto no definidos.")
            return

        self.modbus_tcp_handler.connect(ip, port)
        self.modbus_tcp_handler.set_local()
        
        self.selected_device_handler = self.modbus_tcp_handler

    def on_start_modbus_tcp(self):
        """Detiene servidor Modbus TCP."""
        self.modbus_tcp_handler.start()

    def on_stop_modbus_tcp(self):
        """Reinicia servidor Modbus TCP."""
        self.modbus_tcp_handler.stop()

    def on_reset_modbus_tcp(self):
        """Configura remoto Modbus TCP."""
        self.modbus_tcp_handler.set_remote()

    def on_custom_modbus_tcp(self):
        """Configura local Modbus TCP."""
        self.modbus_tcp_handler.set_local()

    def on_multiple_modbus_tcp(self):
            addresses = list(dict.fromkeys(self.signal_modbus_tcp_dir.values()))
            print(addresses)
            self.modbus_serial_thread = self.modbus_tcp_handler.poll_registers(
                addresses=addresses,
                interval=0.5,
            )

    def on_set_remote_tcp(self):
        self.modbus_tcp_handler.write_register(address=4358, value=2)
    
    def on_modbus_tcp_read_callback(self, regs):
        """Lee según signal_modbus_serial_dir, aplica escala y loguea."""
        signal = self._build_signal_from_regs(regs, self.signal_modbus_tcp_dir)

        labels = {
            "freqRef": "Referencia de frecuencia",
            "accTime": "Tiempo de aceleración",
            "decTime": "Tiempo de desaceleración",
            "curr":    "Amperaje de salida",
            "freq":    "Frecuencia de salida",
            "volt":    "Voltaje de salida",
            "power":   "Potencia en kW",
            "stat":    "Estado",
            "dir":     "Dirección",
        }
        for k, label in labels.items():
            v = signal.get(k, None)
            if v is not None:
                self.window._log(f"⚠️ {label}: {v}")
        self.on_send_signal(signal, "drive")

    # === Logo ===

    def _build_logo_signal_from_regs(self, regs: dict[int, int]) -> dict:
        """
        Build a LOGO! signal dictionary from register values.
        Applies scaling when needed.
        """
        s = {name: regs.get(addr) for name, addr in self.signal_logo_dir.items()}

        # Apply scaling if needed (example: adjust based on actual LOGO! data meaning)
        # Add any specific LOGO! scaling rules here if required

        return s

    def on_logo_read_callback(self, regs):
        """
        Reads registers according to signal_logo_dir and logs values.
        """
        print(regs)
        signal = self._build_logo_signal_from_regs(regs)

        labels = {
            "faultRec": "Voltage fault recovery time",
            "faultRes": "Fault reset time",
            "workHours": "Working hours",
            "workMinutes": "Working minutes",
            "faultLowWater": "Tank Low Water Level Fault",
            "highPressureRes": "High-pressure reset delay",
        }

        for k, label in labels.items():
            v = signal.get(k, None)
            if v is not None:
                self.window._log(f"⚠️ {label}: {v}")

        print(signal)

    def on_multiple_logo(self):
        addresses = list(dict.fromkeys(self.signal_logo_dir.values()))
        print(addresses)
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
        """Read"""
        succeded = self.logo_handler.read_registers(6, 1)
        if(succeded):
            return self.window._log(f"se leyo en la direccion {6}")

    def on_stop_logo(self):
        """Evento STOP para Logo (placeholder)."""
        succeded = self.logo_handler.write_coil(4, 1)
        if(succeded):
            return self.window._log(f"Se apago desde el logo")
        self.window._log("Error al apagar desde el logo")

    def on_start_logo(self):
        """Envía comando RUN a Logo."""
        succeded = self.logo_handler.write_coil(3, 1)
        if(succeded):
            return self.window._log(f"Se encendio desde el logo")
        self.window._log("Error al encender desde el logo")

    def on_reset_logo(self):
        """Evento RESET para Logo (placeholder)."""
        self.window._log("🔁 Logo: Reset presionado.")
