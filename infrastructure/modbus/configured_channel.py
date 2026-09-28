from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional

from pymodbus.client import ModbusSerialClient, ModbusTcpClient


class ConfiguredModbusChannel:
    """Runs one published DeviceProfile channel against one device connection."""

    FAILURE_THRESHOLD = 2

    def __init__(
        self,
        *,
        channel: Dict[str, Any],
        connection: Dict[str, Any],
        on_signal: Callable[[Dict[str, Any], str], None],
        on_status: Callable[[str, bool, Optional[str], list], None],
        log: Callable[[str], None],
    ) -> None:
        self.channel = channel
        self.connection = connection
        self.on_signal = on_signal
        self.on_status = on_status
        self.log = log
        self.channel_id = str(channel["id"])
        self.protocol = channel["protocol"]
        self.slave_id = int(connection.get("slaveId", 1))
        self.poll_interval = max(0.1, float(channel.get("pollIntervalMs", 500)) / 1000)
        self.client = None
        self._io_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_status = None

    @property
    def readable_items(self):
        return [
            item for item in self.channel.get("items", [])
            if item.get("capability") in ("read", "read-write")
            and isinstance(item.get("read"), dict)
        ]

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"modbus-{self.channel_id}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            self._thread.join(timeout=2)
        self._disconnect()

    def is_connected(self) -> bool:
        if not self.client:
            return False
        try:
            if hasattr(self.client, "is_socket_open"):
                return bool(self.client.is_socket_open())
            return bool(getattr(self.client, "connected", False))
        except Exception:
            return False

    def _new_client(self):
        if self.protocol == "modbus-tcp":
            return ModbusTcpClient(
                host=str(self.connection["host"]),
                port=int(self.connection["port"]),
                timeout=1,
                retries=0,
            )
        if self.protocol == "modbus-rtu":
            serial_port = self.connection.get("serialPort") or self.connection.get("interfaceId")
            parity = str(self.connection.get("parity", "N")).upper()[0]
            return ModbusSerialClient(
                port=str(serial_port),
                baudrate=int(self.connection.get("baudRate", 9600)),
                parity=parity,
                stopbits=int(self.connection.get("stopBits", 1)),
                bytesize=int(self.connection.get("dataBits", 8)),
                timeout=1,
                retries=0,
            )
        raise ValueError(f"Unsupported protocol: {self.protocol}")

    def _connect(self) -> bool:
        self._disconnect()
        try:
            self.client = self._new_client()
            if self.client.connect():
                self.log(f"✅ Canal {self.channel_id} conectado ({self.protocol}).")
                return True
        except Exception as error:
            self.log(f"❌ Canal {self.channel_id}: {type(error).__name__} al conectar.")
        self._disconnect()
        return False

    def _disconnect(self) -> None:
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        self.client = None

    def _publish_status(self, connected: bool, reason=None, failed=None) -> None:
        status = (connected, reason, tuple((entry["itemId"], entry["address"]) for entry in failed or []))
        if status != self._last_status:
            self._last_status = status
            self.on_status(self.channel_id, connected, reason, failed or [])

    def _run(self) -> None:
        failed_cycles = 0
        while not self._stop_event.is_set():
            if not self.is_connected() and not self._connect():
                self._publish_status(False, "connection_failed")
                self._stop_event.wait(5)
                continue

            payload = {}
            failures = []
            for item in self.readable_items:
                address = int(item["read"]["address"])
                raw = self.read_register(address)
                if raw is None:
                    failures.append({"itemId": item["id"], "address": address})
                    continue
                payload[item["id"]] = self._decode(item, raw)

            if payload:
                failed_cycles = 0
                reason = "partial_modbus_failure" if failures else None
                self._publish_status(True, reason, failures)
                self.on_signal(payload, self.channel_id)
            else:
                failed_cycles += 1
                if failed_cycles >= self.FAILURE_THRESHOLD:
                    self._publish_status(False, "modbus_no_response", failures)
                    self._disconnect()
            self._stop_event.wait(self.poll_interval)

    def read_register(self, address: int) -> Optional[int]:
        if not self.client:
            return None
        with self._io_lock:
            try:
                response = self.client.read_holding_registers(
                    address, count=1, device_id=self.slave_id
                )
                if response and not response.isError():
                    return int(response.registers[0])
            except Exception as error:
                self.log(
                    f"⚠️ Canal {self.channel_id}: {type(error).__name__} leyendo {address}."
                )
        return None

    def write_register(self, address: int, value: int) -> bool:
        if not self.client:
            return False
        with self._io_lock:
            try:
                response = self.client.write_register(
                    address, value & 0xFFFF, device_id=self.slave_id
                )
                return bool(response and not response.isError())
            except Exception as error:
                self.log(
                    f"⚠️ Canal {self.channel_id}: {type(error).__name__} escribiendo {address}."
                )
                return False

    @staticmethod
    def _decode(item: Dict[str, Any], raw: int) -> Dict[str, Any]:
        read = item["read"]
        value: Any = raw
        if read.get("signed") and raw >= 0x8000:
            value = raw - 0x10000
        value = value * float(read.get("scale", 1))
        if read.get("absolute"):
            value = abs(value)
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return {
            "value": value,
            "rawValue": raw,
            "kind": item.get("kind", "operation"),
        }

    def execute_action(self, item_id: str, action_id: str) -> tuple[bool, Optional[str]]:
        # Keep read-modify-write atomic with respect to polling and other actions.
        with self._io_lock:
            return self._execute_action_locked(item_id, action_id)

    def _execute_action_locked(self, item_id: str, action_id: str) -> tuple[bool, Optional[str]]:
        item = next(
            (candidate for candidate in self.channel.get("items", []) if candidate.get("id") == item_id),
            None,
        )
        actions = (item or {}).get("write", {}).get("actions", [])
        action = next((candidate for candidate in actions if candidate.get("id") == action_id), None)
        if not action:
            return False, "configured_action_not_found"
        if not self.is_connected():
            return False, "channel_not_connected"
        address = int(action["address"])
        value = int(action["value"])
        if action.get("writeMode", "replace") == "masked":
            current = self.read_register(address)
            if current is None:
                return False, "masked_write_read_failed"
            mask = int(action["mask"])
            value = (current & ~mask) | (value & mask)
        if not self.write_register(address, value):
            return False, "device_write_failed"
        return True, None
