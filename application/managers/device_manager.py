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
        batches = {}
        expected_total = None

        def _cb(c,u,m):
            nonlocal expected_total
            try:
                data = json.loads(m.payload.decode("utf-8"))
                devices = data["devices"]
                if not isinstance(devices, list):
                    raise ValueError("Se esperaba una lista de dispositivos.")
                total = data.get("total", 1)
                index = data.get("index", 0)
                if not isinstance(total, int) or total < 1 or not isinstance(index, int) or not 0 <= index < total:
                    raise ValueError("Lote de dispositivos inválido.")
                if expected_total != total:
                    batches.clear()
                    expected_total = total
                batches[index] = devices
                if len(batches) < total:
                    return False
                self.set_devices([device for batch in range(total) for device in batches[batch]])
                return True
            except Exception as error:
                self.log(f"❌ No se pudo procesar la configuración de dispositivos: {type(error).__name__}.")
                return False

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
        publish_applied = getattr(self.mqtt_client, "publish_device_config_applied", None)
        if callable(publish_applied) and not publish_applied(devices):
            self.log("⚠️ No se pudo confirmar la configuración aplicada al backend.")
        self.log(f"Configuración cargada: {len(devices)} dispositivo(s). Conexiones iniciadas.")
