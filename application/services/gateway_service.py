# application/services/gateway_service.py

from domain.models.gateway import Gateway

class GatewayService:
    """
    Application service for registering and managing gateway lifecycle.
    Orchestrates MQTT communication and persistence via GatewayManager.
    """

    def __init__(self, gateway_manager, mqtt_client, log_func=None):
        """
        :param gateway_manager: Manager responsible for loading/saving gateways
        :param mqtt_client: MQTT client driver to publish gateway registration
        :param log_func: Optional logging function
        """
        self.gateway_manager = gateway_manager
        self.mqtt_client = mqtt_client
        self.log = log_func or (lambda msg: print(msg))

    def create_gateway(self, name: str, organization_id: str, location: str) -> Gateway:
        """
        Register a new gateway by publishing a registration request over MQTT
        and persisting it locally via the GatewayManager.

        :param name: Human-readable name of the gateway
        :param organization_id: Tenant organization ID
        :param location: Physical location description
        :return: The Gateway domain model instance
        """
        # Publish registration request over MQTT
        self.log(f"▶ Publishing gateway registration for '{name}'…")
        self.mqtt_client.send_gateway(name, organization_id, location)

        # Check if a gateway already exists in local store
        existing = self.gateway_manager.get_by_id(organization_id)
        if existing:
            # Update existing gateway record
            gateway = Gateway(
                name=name,
                organizationId=organization_id,
                location=location,
                gatewayId=existing.gatewayId
            )
            updated = self.gateway_manager.update_gateway(gateway)
            if updated:
                self.log(f"✅ Gateway '{name}' updated locally.")
            else:
                self.log(f"❌ Failed to update gateway '{name}'.")
        else:
            # Create and save a new gateway record
            # Let GatewayManager assign or validate gatewayId as needed
            gateway = Gateway(
                name=name,
                organizationId=organization_id,
                location=location,
                gatewayId=None  # manager will generate one if necessary
            )
            added = self.gateway_manager.add_gateway(gateway)
            if added:
                self.log(f"🆕 Gateway '{name}' added locally.")
            else:
                self.log(f"⚠️ Gateway '{name}' may already exist.")

        return gateway


