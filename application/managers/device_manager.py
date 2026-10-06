import json
from infrastructure.activity_log import log_value, profile_summary

class DeviceManager:
    def __init__(self, mqtt_client, refresh_devices, log_func=None):
        # Initialize the DeviceManager with an optional logging function
        self.log = log_func or (lambda msg: print(msg))
        self.devices = []
        self.mqtt_client = mqtt_client
        self.refresh_devices = refresh_devices

    def load_devices(self):
        def _cb(c,u,m):
            try:
                data = json.loads(m.payload.decode("utf-8"))
                self.set_devices(data["devices"])
            except Exception as error:
                self.log(f"❌ No se pudo procesar la configuración de dispositivos: {type(error).__name__}.")

        try:
            self.mqtt_client.request_devices(
                _cb
            )
        except Exception as e:
            self.log(f"⚠️ MQTT fetch failed: {e}")
            return None
    def set_devices(self, devices: list):
        if not isinstance(devices, list) or any(not isinstance(d, dict) for d in devices):
            raise ValueError('Se esperaba una lista de dispositivos.')
        self.log(f"Configuración recibida por MQTT: {len(devices)} dispositivo(s).")
        for device in devices:
            self.log(
                f"Dispositivo {log_value(device.get('serialNumber'))}, "
                f"nombre={log_value(device.get('name'))}; "
                f"conexiones={len(device.get('connections') or [])}; "
                f"perfil: {profile_summary(device.get('deviceProfileId'))}"
            )
        self.devices = devices
        self.refresh_devices(devices)
        self.log(f"Configuración cargada: {len(devices)} dispositivo(s). Conexiones iniciadas.")
