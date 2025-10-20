from application.services.device.device_service import DeviceService

class DeviceController:
    def __init__(self, mqtt_handler, gateway_cfg, log, window=None):
        self.mqtt = mqtt_handler
        self.gateway_cfg = gateway_cfg
        self.log = log
        self.window = window  # opcional, solo si querés refrescar UI directamente
        self.devices = {}
        self.services = []

    def create_all(self, devices=None):
        """
        (Re)crea todos los DeviceService a partir de la lista de dispositivos recibida.
        Detiene los servicios previos, inicializa los nuevos y actualiza la UI.
        """
        devices = devices or []
        total = len(devices)

        # 🔻 Detener servicios anteriores
        if self.devices:
            self.log(f"🛑 Deteniendo {len(self.devices)} DeviceService anteriores...")
            for ds in self.devices.values():
                try:
                    ds.stop()
                except Exception as e:
                    self.log(f"⚠️ Error deteniendo DeviceService: {e}")

        # 🔹 Crear nuevas instancias DeviceService
        device_services = {}
        created = 0
        for dev in devices:
            try:
                ds = DeviceService(
                    mqtt_handler=self.mqtt,
                    gateway_cfg=self.gateway_cfg,
                    device=dev,
                    log=self.log,
                    update_fields=None,  # Ya no se usa directamente
                )
                device_services[ds.serial] = ds
                created += 1
            except Exception as e:
                name = dev.get("name") or dev.get("serialNumber") or "desconocido"
                self.log(f"❌ Error creando DeviceService para '{name}': {e}")

        # 🔸 Actualizar estado interno
        self.devices = device_services
        self.services = list(self.devices.values())

        # 🔸 Actualizar interfaz si está disponible
        if self.window:
            try:
                self.window.update_device_list(self.services)
            except Exception as e:
                self.log(f"⚠️ No se pudo actualizar la UI: {e}")

        # ✅ Log final
        self.log(f"📡 DeviceService creados correctamente: {created}/{total}")

    def handle_command(self, device_serial, command):
        """Ejecuta comandos recibidos sobre un DeviceService."""
        ds = self.devices.get(device_serial)
        print("DEVICE FOUND", ds)
        if not ds:
            self.log(f"⚠️ Device {device_serial} no encontrado.")
            return

        action = command.get("action")
        params = command.get("params", {})

        match action:
            case "update-connections":
                ds.update_connection_config(params)
            case "update-status":

                value = str(params.get("value", "")).lower()
                if value == "on": ds.turn_on()
                elif value == "off": ds.turn_off()
                elif value == "restart": ds.restart()
            case _:
                self.log(f"⚙️ Unknown device command: {action}")
