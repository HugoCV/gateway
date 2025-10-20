from infrastructure.config.loader import get_gateway, save_gateway

class GatewayController:
    def __init__(self, log):
        self.log = log
        self.config = get_gateway()

    def save(self, org_id, gw_id):
        self.config["organizationId"] = org_id
        self.config["gatewayId"] = gw_id
        save_gateway(self.config)
        self.log("✅ Gateway config saved.")

    def update_networks(self, new_networks):
        self.config["known_networks"] = new_networks
        save_gateway(self.config)
        self.log("📡 Networks updated.")
