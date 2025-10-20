from domain.models.device import Device
import json

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
                if(not data["devices"]):
                    return
                self.set_devices(data["devices"])
            except Exception:
                data = None

        try:
            self.mqtt_client.request_devices(
                _cb
            )
        except Exception as e:
            self.log(f"⚠️ MQTT fetch failed: {e}")
            return None
    def set_devices(self, devices: list):
        self.devices = devices
        self.refresh_devices(devices)

