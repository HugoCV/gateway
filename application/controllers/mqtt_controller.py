class MqttController:
    def __init__(self, gateway_cfg, log, on_load, on_command, on_gateway_command):
        from infrastructure.mqtt.mqtt_client import MqttClient
        self.mqtt = MqttClient(
            gateway_cfg,
            on_load,
            log_callback=log,
            command_callback=on_command,
            command_gateway_callback=on_gateway_command
        )

    def connect(self):
        self.mqtt.connect()
