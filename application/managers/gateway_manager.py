import json
from domain.models.gateway import Gateway

class GatewayManager:
    """
    Manager for loading, saving updating a Gateway.
    Receives an MQTT client to publish registration messages.
    """

    def __init__(self, mqtt_client, refresh_gateway, log_func=None):
        """
        Initialize GatewayManager.

        :param mqtt_client: MQTT client driver for publishing gateway updates
        :param log_func: Optional logging function
        """
        self.mqtt_client = mqtt_client
        self.log = log_func or (lambda msg: print(msg))
        self.refresh_gateway = refresh_gateway
        self._gateway = None
        # self._load_gateway()
    
    def set_gateway(self, gateway: dir):
        self._gateway = gateway
        self.refresh_gateway(gateway)
        
    def load_gateway(self):
        self.log(f"Loading gateway")
        def _cb(c,u,m):
            try:
                data = json.loads(m.payload.decode("utf-8"))
                self.set_gateway(data)
            except Exception:
                data = None

        try:
            self.mqtt_client.request_gateway_config(
                _cb
            )
        except Exception as e:
            self.log(f"⚠️ MQTT fetch failed: {e}")
            return None


    def get_gateway(self) -> Gateway:
        """
        Return the current Gateway model or None if not set.
        """
        return self._gateway

