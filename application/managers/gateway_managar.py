import json
import os
from domain.gateway import Gateway

GATEWAY_FILE = os.path.join("data", "gateway.json")


class GatewayManager:
    def __init__(self, log_func=None):
        self.log = log_func or (lambda msg: print(msg))
        self._gateway = self._load_gateway()

    def _load_gateway(self):
        try:
            with open(GATEWAY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return Gateway(**data)
                else:
                    self.log("⚠️ gateway.json no contiene un objeto válido.")
        except FileNotFoundError:
            self.log("⚠️ No se encontró gateway.json.")
        except json.JSONDecodeError:
            self.log("⚠️ Error al leer gateway.json.")
        return None

    def _save_gateway(self):
        if self._gateway is None:
            self.log("❌ No hay gateway para guardar.")
            return

        os.makedirs(os.path.dirname(GATEWAY_FILE), exist_ok=True)
        with open(GATEWAY_FILE, "w", encoding="utf-8") as f:
            json.dump(self._gateway.to_dict(), f, indent=2, ensure_ascii=False)
        self.log("💾 Gateway guardado correctamente.")

    def get_gateway(self):
        return self._gateway

    def set_gateway(self, gateway: Gateway):
        self._gateway = gateway
        self._save_gateway()

    def update_gateway(self, updated: Gateway):
        if self._gateway and self._gateway.gatewayId == updated.gatewayId:
            self._gateway = updated
            self._save_gateway()
            self.log(f"✅ Gateway actualizado: {updated.name}")
            return True
        self.log("❌ Gateway no coincide o no existe.")
        return False

    def delete_gateway(self):
        self._gateway = None
        if os.path.exists(GATEWAY_FILE):
            os.remove(GATEWAY_FILE)
        self.log("🗑 Gateway eliminado.")
