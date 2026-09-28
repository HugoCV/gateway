from __future__ import annotations

from threading import RLock
from typing import Any, Dict, Optional

from infrastructure.modbus.configured_channel import ConfiguredModbusChannel


class DeviceService:
    """Runs enabled channels for active and commissioning devices."""

    def __init__(self, *, mqtt_handler, gateway_cfg, device, log, update_fields) -> None:
        self.mqtt = mqtt_handler
        self.gateway_cfg: Dict[str, Any] = gateway_cfg
        self.device: Dict[str, Any] = device or {}
        self.log = log
        self.update_fields = update_fields
        self._lock = RLock()
        self.device_id = str(
            self.device.get("_id")
            or self.device.get("serialNumber")
            or self.device.get("name")
            or ""
        )
        self.name = self.device.get("name", "desconocido")
        self.serial = self.device.get("serialNumber", "")
        self.profile = self.device.get("deviceProfileId") or {}
        self.connections = self.device.get("connections") or []
        self.channels: Dict[str, ConfiguredModbusChannel] = {}
        self.channel_status: Dict[str, bool] = {}
        self.connected = False
        self.connected_logo = False
        # Kept for the local status window; configuration now lives per channel.
        self.cc = {}
        self._build_channels()
        self.start()

    def __del__(self):
        self.stop()

    def _build_channels(self) -> None:
        if self.device.get("commissioningStatus") not in {"active", "commissioning"}:
            return
        definitions = {
            channel.get("id"): channel
            for channel in self.profile.get("channels", [])
            if isinstance(channel, dict) and channel.get("id")
        }
        for connection in self.connections:
            if not isinstance(connection, dict) or connection.get("enabled") is False:
                continue
            channel_id = connection.get("channelId")
            channel = definitions.get(channel_id)
            if not channel:
                self.log(f"⚠️ {self.serial}: conexión para canal desconocido {channel_id}.")
                continue
            try:
                self.channels[channel_id] = ConfiguredModbusChannel(
                    channel=channel,
                    connection=connection,
                    on_signal=self._send_signal,
                    on_status=self._on_channel_status,
                    log=self.log,
                )
            except (KeyError, TypeError, ValueError) as error:
                self.log(
                    f"⚠️ {self.serial}: canal {channel_id} inválido ({type(error).__name__})."
                )

    def start(self) -> None:
        for channel in self.channels.values():
            channel.start()

    def stop(self) -> None:
        for channel in list(getattr(self, "channels", {}).values()):
            try:
                channel.stop()
            except Exception as error:
                self.log(f"⚠️ Error deteniendo canal: {type(error).__name__}.")

    def _on_channel_status(
        self, channel_id: str, connected: bool, reason: Optional[str], failed_items: list
    ) -> None:
        self.channel_status[channel_id] = connected
        minimum = int(
            (self.profile.get("connectionPolicy") or {}).get(
                "minimumEnabledChannels", 1
            )
        )
        self.connected = sum(bool(value) for value in self.channel_status.values()) >= minimum
        self.connected_logo = self.channel_status.get("logo", False)
        failed_registers = [
            {"name": entry["itemId"], "address": entry["address"]}
            for entry in failed_items
        ]
        self.mqtt.on_change_device_connection(
            self.serial,
            "online" if self.connected else "offline",
            "online" if self.connected_logo else "offline",
            reason,
            channel_id,
            failed_registers,
            channel_status="online" if connected else "offline",
        )

    def execute_action(
        self, channel_id: str, item_id: str, action_id: str
    ) -> tuple[bool, Optional[str]]:
        channel = self.channels.get(channel_id)
        if not channel:
            return False, "channel_not_enabled"
        return channel.execute_action(item_id, action_id)

    def update_connections(self, connections) -> None:
        if not isinstance(connections, list):
            raise ValueError("connections must be a list")
        with self._lock:
            self.stop()
            self.connections = connections
            self.device["connections"] = connections
            self.channels = {}
            self.channel_status = {}
            self._build_channels()
            self.start()
        self.log(f"Configuración de conexiones aplicada a {self.serial}.")
        if self.update_fields:
            self.update_fields(self)

    def _ids(self):
        organization_id = self.gateway_cfg.get("organization_id") or self.gateway_cfg.get("organizationId")
        gateway_id = self.gateway_cfg.get("gateway_id") or self.gateway_cfg.get("gatewayId")
        return organization_id, gateway_id

    def _send_signal(self, results: Dict[str, Any], channel_id: str) -> None:
        if not isinstance(results, dict) or not results:
            return
        organization_id, gateway_id = self._ids()
        if not organization_id or not gateway_id:
            self.log("⚠️ No se pueden publicar señales sin identidad del gateway.")
            return
        self.mqtt.send_signal(
            {
                "serial_number": self.serial,
                "organization_id": organization_id,
                "gateway_id": gateway_id,
            },
            {"channelId": channel_id, "payload": results},
        )
