import threading
import time
import requests

class HttpClient:
    def __init__(self, app, base_url):
        self.app = app
        self.base_url = base_url
        self.running = False
        self.interval = 5

        self.endpoints = {
            "drive": f"{self.base_url}/drive/stat",
            "mntr": f"{self.base_url}/mntr/stat",
            "dashboard": f"{self.base_url}/stat"
        }

    def start_continuous_read(self, interval=5):
        self.interval = interval
        self.running = True

        def read_loop():
            while self.running:
                for group, url in self.endpoints.items():
                    data = self.read_http_data(url)
                    if data:
                        signal = {
                            "group": group,
                            "payload": data
                        }
                        self.send_signal(signal)
                time.sleep(self.interval)

        threading.Thread(target=read_loop, daemon=True).start()

    def stop_continuous_read(self):
        self.running = False

    def read_http_data(self, url):
        try:
            response = requests.get(url, timeout=3)
            if response.ok:
                return response.json()
            print(f"⚠️ Error HTTP {response.status_code} al leer {url}")
        except Exception as e:
            print(f"❌ Excepción al hacer GET {url}: {e}")
        return None

    def send_signal(self, signal_info):
        try:
            device_serial = self.app.serial_var.get().strip()
            gateway_id = self.app.gateway_cfg.get("gatewayId")
            organization_id = self.app.gateway_cfg.get("organizationId")

            topic_info = {
                "gateway_id": gateway_id,
                "organization_id": organization_id,
                "serial_number": device_serial
            }

            self.app.gateway.send_signal(topic_info, signal_info)
        except Exception as e:
            print(f"❌ Error al enviar señal: {e}")
