import time
import threading
from pymodbus.client import ModbusTcpClient
from tkinter import messagebox

class ModbusTcp:
    def __init__(self, controller, log):
        self.controller = controller
        self.client = None
        self.log = log

    def connect(self, ip, port) -> bool:
        self.log(f"🔌 Iniciando conexión {ip}:{port}")
        try:
            port = int(port)

            # Cierra cliente previo si existía
            if getattr(self, "client", None):
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None

            self.client = ModbusTcpClient(host=ip, port=port, timeout=3.0)

            if not self.client.connect():
                self.log(f"❌ No se pudo conectar a {ip}:{port}")
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None
                return False

            self.log(f"✅ Conectado a {ip}:{port}")

            # Prueba de escritura (opcional)
            rr = self.client.write_register(address=4358, value=4)
            if rr is None or rr.isError():
                self.log("⚠️ Conectado, pero falló write_register(4358, 2)")
            else:
                self.log("📝 write_register(4358, 2) OK")

            return True

        except Exception as e:
            self.log(f"❌ Error conectando a {ip}:{port}: {e}")
            try:
                if self.client:
                    self.client.close()
            except Exception:
                pass
            self.client = None
            return False

    def start(self):
        if self.client:
            result = self.client.write_register(address=898, value=3)
            self.log(f"resultado {result}")
            if not result.isError():
                self.log("✔ Comando enviado: RUN")

    def stop(self):
        if self.client:
            result = self.client.write_register(address=898, value=0)
            self.log(f"resultado {result}")
            if not result.isError():
                self.log("✔ Comando enviado: STOP")
    
    def reset(self):
        if self.client:
            result1 = self.client.write_register(address=901, value=1)
            result2 = self.client.write_register(address=901, value=0)
            result3 = self.client.write_register(address=898, value=2)
            
            if not result1.isError() and not result2.isError() and not result3.isError():
                self.log("✔ Comando enviado: RESET")

    def set_local(self):
        self.remoto = self.client.write_register(address=4358, value=2)

    def set_remote(self):
        self.remoto = self.client.write_register(address=4358, value=4)
        
    def write_register(self, address: int, value: int):
        self.client.write_register(address=address, value=value)

    def start_continuous_read(self):
        def read_loop():
            while True:
                if self.client:
                    rr = self.client.read_holding_registers(address=19, count=9)
                    print(rr)
                time.sleep(5)
        threading.Thread(target=read_loop, daemon=True).start()

    def send_signal(self, signal_info):
        device_serial = self.controller.serial_var.get().strip()
        gw_id = self.controller.gateway_cfg.get("gatewayId")
        or_id = self.controller.gateway_cfg.get("organizationId")
        topic_info = {
            "gateway_id": gw_id,
            "organization_id": or_id,
            "serial_number": device_serial
        }
        self.controller.gateway.send_signal(topic_info, signal_info)
