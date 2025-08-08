import json
import os
from domain.models.gateway import Gateway

class GatewayManager:
    """
    Manager for loading, saving updating a Gateway.
    Receives an MQTT client to publish registration messages.
    """

    def __init__(self, mqtt_client, log_func=None):
        """
        Initialize GatewayManager.

        :param mqtt_client: MQTT client driver for publishing gateway updates
        :param log_func: Optional logging function
        """
        self.mqtt_client = mqtt_client
        self.log = log_func or (lambda msg: print(msg))
        self._gateway = None
        # self._load_gateway()
        

    def _load_gateway(self):
        """
        Internal: load gateway configuration via MQTT, fallback to JSON file if necessary.
        """
        # Attempt to fetch gateway config from MQTT
        try:
            data = self.mqtt_client.request_gateway_config()
            print("gateway manager", data)
            if data:
                # self._gateway = Gateway(**data)
                self.log(f"📡 Loaded gateway via MQTT: '{self._gateway.name}'")
                return data
            self.log("⚠️ No gateway configuration received via MQTT.")
        except Exception as e:
            self.log(f"⚠️ MQTT fetch failed: {e}")

    def _save_gateway(self):
        """
        Internal: persist current gateway to JSON file.
        """
        if not self._gateway:
            self.log("⚠️ No gateway to save.")
            return
        os.makedirs(os.path.dirname(GATEWAY_FILE), exist_ok=True)
        with open(GATEWAY_FILE, 'w', encoding='utf-8') as f:
            json.dump(self._gateway.to_dict(), f, indent=2, ensure_ascii=False)
        self.log(f"💾 Saved gateway '{self._gateway.name}' to file.")

    def get_gateway(self) -> Gateway:
        """
        Return the current Gateway model or None if not set.
        """
        return self._gateway

    def register_gateway(self, name: str, organization_id: str, location: str) -> Gateway:
        """
        Create or update the Gateway model and publish registration via MQTT.

        :param name: Gateway name
        :param organization_id: Tenant organization ID
        :param location: Physical location
        :return: The registered Gateway instance
        """
        # Build or update Gateway model
        if self._gateway and self._gateway.organizationId == organization_id:
            self._gateway.name = name
            self._gateway.location = location
            self.log(f"🔄 Updated gateway '{name}'.")
        else:
            # Generate ID if missing in Gateway constructor
            self._gateway = Gateway(
                name=name,
                organizationId=organization_id,
                location=location,
                gatewayId=None
            )
            self.log(f"🆕 Created new gateway '{name}'.")

        # Persist locally
        self._save_gateway()

        # Publish registration request over MQTT
        try:
            self.mqtt_client.send_gateway(
                self._gateway.name,
                self._gateway.organizationId,
                self._gateway.location
            )
            self.log(f"📤 Published gateway registration for '{name}'.")
        except Exception as e:
            self.log(f"❌ Error publishing gateway registration: {e}")

        return self._gateway

    def delete_gateway(self) -> bool:
        """
        Remove the current gateway and delete the JSON file.

        :return: True if deleted, False otherwise
        """
        if not self._gateway:
            self.log("⚠️ No gateway to delete.")
            return False
        try:
            os.remove(GATEWAY_FILE)
            self.log(f"🗑️ Deleted gateway file.")
        except OSError as e:
            self.log(f"❌ Error deleting gateway file: {e}")
            return False
        self._gateway = None
        return True
