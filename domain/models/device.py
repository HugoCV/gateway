# domain/models/device.py

from typing import List
from domain.models.signal import Signal

class Device:
    """
    Entidad de dominio Device.
    Representa un dispositivo conectado a un gateway,
    con su serial, nombre, modelo y colección de señales.
    """
    def __init__(
        self,
        serial_number: str,
        name: str,
        model: str,
        gateway_id: str,
        organization_id: str,
        signals: List[Signal] = None
    ):
        self.serial_number = serial_number
        self.name = name
        self.model = model
        self.gateway_id = gateway_id
        self.organization_id = organization_id
        # Lista de señales (Signal es otra entidad de dominio)
        self.signals: List[Signal] = signals or []

    def add_signal(self, signal: Signal) -> None:
        """Agrega una nueva señal al dispositivo."""
        self.signals.append(signal)

    def get_signal(self, name: str) -> Signal:
        """Obtiene una señal por su nombre, o None si no existe."""
        return next((s for s in self.signals if s.name == name), None)

    def to_dict(self) -> dict:
        """Serializa el dispositivo a un dict plano (para JSON, DTOs, etc.)."""
        return {
            "serialNumber": self.serial_number,
            "name": self.name,
            "model": self.model,
            "gatewayId": self.gateway_id,
            "organizationId": self.organization_id,
            "signals": [s.to_dict() for s in self.signals],
        }
