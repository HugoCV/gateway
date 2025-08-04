# drivers/logo_modbus.py
from pymodbus.client import ModbusTcpClient

class LogoModbusClient:
    def __init__(self, host, port=502):
        self.host = host
        self.port = port
        self.client = ModbusTcpClient(host=self.host, port=self.port)

    def connect(self):
        return self.client.connect()

    def disconnect(self):
        self.client.close()

    def read_holding_registers(self, address, count=1, unit=1):
        return self.client.read_holding_registers(address=address, count=count, unit=unit)

    def write_single_register(self, address, value, unit=1):
        return self.client.write_register(address, value, unit=unit)

    def is_connected(self):
        return self.client.is_socket_open()


# drivers/logo_http.py
import requests

class LogoHttpClient:
    def __init__(self, base_url, username=None, password=None):
        self.base_url = base_url.rstrip('/')
        self.auth = (username, password) if username and password else None

    def get_page(self, path="/"):
        url = f"{self.base_url}{path}"
        try:
            response = requests.get(url, auth=self.auth, timeout=5)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"[LogoHttpClient] HTTP Error: {e}")
            return None

    def get_status_snapshot(self):
        """Example: parse a specific LOGO! Web page if you know the HTML layout."""
        html = self.get_page("/status.html")
        if not html:
            return None

        # NOTE: You must customize this depending on the LOGO! HTML content
        # Here we just return the raw HTML for now
        return html
