from typing import List, Optional

class Device:
    """
    Entity representing a Device under a Gateway.
    Contains configuration for HTTP, Modbus TCP and Serial, plus metadata and signals.
    """
    def __init__(
        self,
        name: str,
        serial_number: str,
        model: str,
        device_type: str,
        ip_address: str = "",
        ip_port: str = "",
        tcp_ip: str = "",
        tcp_port: str = "",
        serial_port: str = "",
        baudrate: Optional[int] = None,
        slave_id: Optional[int] = None,
    ):
        self.name = name
        self.serial_number = serial_number
        self.model = model
        self.type = device_type

        # HTTP config
        self.ip_address = ip_address
        self.ip_port = ip_port

        # Modbus TCP config
        self.tcp_ip = tcp_ip
        self.tcp_port = tcp_port

        # Modbus Serial config
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.slave_id = slave_id


    def to_dict(self) -> dict:
        """Serialize the device to a plain dictionary."""
        return {
            "name": self.name,
            "serialNumber": self.serial_number,
            "model": self.model,
            "type": self.type,
            "ip_address": self.ip_address,
            "ip_port": self.ip_port,
            "tcp_ip": self.tcp_ip,
            "tcp_port": self.tcp_port,
            "serial_port": self.serial_port,
            "baudrate": self.baudrate,
            "slave_id": self.slave_id,
        }
