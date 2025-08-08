import time
import threading
import requests
from pymodbus.client.sync import ModbusTcpClient


class DeviceService:
    def __init__(self,
                 modbus_host='localhost', modbus_port=5020,
                 http_host='localhost',  http_port=8000,
                 modbus_unit_id=1):
        # Cliente Modbus TCP
        self.modbus_client = ModbusTcpClient(modbus_host, port=modbus_port)
        self.unit_id = modbus_unit_id
        # URL del endpoint HTTP
        self.http_url = f'http://{http_host}:{http_port}/status'

    def get_status_modbus(self):
        """
        Lee los primeros 9 registros vía Modbus y devuelve un dict con claves.
        """
        rr = self.modbus_client.read_holding_registers(address=0, count=9, unit=self.unit_id)
        if rr.isError():
            return {'error': str(rr)}
        regs = rr.registers
        keys = ['stat','freqRef','freq','current','speed','accTime','decTime','speedRef','dir']
        return dict(zip(keys, regs))

    def get_status_http(self, timeout=5):
        """
        Obtiene el estado en formato JSON desde el endpoint HTTP.
        """
        try:
            resp = requests.get(self.http_url, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            return {'error': str(e)}

    def start_http_polling(self, callback, interval=1):
        """
        Inicia un hilo daemon que hace polling al endpoint HTTP cada `interval` segundos
        y llama a `callback(status)` con el JSON recibido.
        """
        def _poll_loop():
            while True:
                status = self.get_status_http()
                callback(status)
                time.sleep(interval)

        thread = threading.Thread(target=_poll_loop, daemon=True)
        thread.start()
        return thread


if __name__ == '__main__':
    # Ejemplo de uso
    def print_status(s):
        print(s)

    ds = DeviceService(
        modbus_host='192.168.1.50', modbus_port=5020,
        http_host='192.168.1.50',  http_port=8000,
        modbus_unit_id=1
    )
    ds.start_http_polling(print_status, interval=2)
    # Mantener el main thread vivo
    while True:
        time.sleep(1)
