
import time
import threading
from pymodbus.client import ModbusTcpClient
from tkinter import messagebox

class ModbusTcp:
    def __init__(self, app):
        self.app = app
        self.client = None

    def connect_device(self, ip, port):
        self.client = ModbusTcpClient(ip, port=port)
        if not self.client.connect():
            messagebox.showerror("Error", f"No se pudo conectar a {ip}:{port}")
            self.client = None
            return
        print(f"✅ Conectado a {ip}:{port}")
        self.remoto = self.client.write_register(address=4358, value=4)
        self.start_continuous_read()

    def start(self):
        print("start")
        if self.client:
            result = self.client.write_register(address=898, value=3)
            print("resultado", result)
            if not result.isError() and not result.isError():
                print("✔ Comando enviado: RUN")

    def stop(self):
        if self.client:
            result = self.client.write_register(address=898, value=0)
            print("resultado", result)
            if not result.isError() and not result.isError():
                print("✔ Comando enviado: STOP")
    
    def reset(self):
        if self.client:
            result1 = self.client.write_register(address=901, value=1)
            result2 = self.client.write_register(address=901, value=0)
            result3 = self.client.write_register(address=898, value=2)
            
            if not result1.isError() and not result2.isError() and not result3.isError():
                print("✔ Comando enviado: RESET")

    def set_local(self):
        self.remoto = self.client.write_register(address=4358, value=2)
    def set_remote(self):
        self.remoto = self.client.write_register(address=4358, value=4)
    def start_continuous_read(self):
        def read_loop():
            while True:
                if self.client:
                    rr = self.client.read_holding_registers(address=19, count=9)
                    print(rr)
                time.sleep(5)
        threading.Thread(target=read_loop, daemon=True).start()

    def send_signal(self, signal_info):
        device_serial = self.app.serial_var.get().strip()
        gw_id = self.app.gateway_cfg.get("gatewayId")
        or_id = self.app.gateway_cfg.get("organizationId")
        topic_info = {
            "gateway_id": gw_id,
            "organization_id": or_id,
            "serial_number": device_serial
        }
        self.app.gateway.send_signal(topic_info, signal_info)
