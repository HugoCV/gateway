
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
        # valores iniciales
        self.client.write_register(address=1, value=500)
        self.client.write_register(address=2, value=200)
        self.client.write_register(address=3, value=300)
        print("✔ Frecuencia inicial escrita")
        self.start_continuous_read()

    def start(self):
        if self.client:
            self.client.write_register(address=0, value=1)
            self.client.write_register(address=1, value=500)
            print("✔ Comando enviado: RUN")

    def stop(self):
        if self.client:
            self.client.write_register(address=0, value=0)
            print("✔ Comando enviado: STOP")

    def start_continuous_read(self):
        def read_loop():
            while True:
                if self.client:
                    rr = self.client.read_holding_registers(address=0, count=4)
                    if not rr.isError():
                        state, freq_ref, freq_actual, current = rr.registers
                        signal_info = {
                            "stat": state,
                            "dir": "stop",
                            "speed": "0",
                            "speedRef": "1110",
                            "accTime": "3.0",
                            "decTime": "4.0",
                            "freq": freq_actual,
                            "freqRef": freq_ref
                        }
                        self.send_signal(signal_info)
                        print(f"[READ] Estado:{state} Frec.Actual:{freq_actual/100:.2f}Hz Frec.Ref:{freq_ref/100:.2f}Hz Corriente:{current/100:.2f}A")
                time.sleep(10)
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
