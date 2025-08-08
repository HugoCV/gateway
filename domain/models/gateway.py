from dataclasses import dataclass, field
from uuid import uuid4
from typing import Optional

@dataclass
class Gateway:
    """
    Domain model representing a Gateway.
    """
    name: str
    modbus_host: str
    modbus_port: int
    http_host: str
    http_port: int
    unit_id: Optional[int] = 1
    description: Optional[str]  = None
    id: str = field(default_factory=lambda: str(uuid4()))

    def endpoint_url(self) -> str:
        return f"http://{self.http_host}:{self.http_port}"

    def status_path(self) -> str:
        return f"{self.endpoint_url()}/status"

    def modbus_address(self) -> tuple:
        return (self.modbus_host, self.modbus_port)
