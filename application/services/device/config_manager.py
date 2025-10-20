from typing import Dict, Any

class ConfigManager:
    """Handles dynamic update of connectionConfig for a DeviceService."""

    _ALLOWED_KEYS = {
        "host", "tcpPort", "serialPort", "baudrate", "slaveId",
        "logoIp", "logoPort", "mode"
    }

    def __init__(self, log, update_fields):
        self.log = log
        self.update_fields = update_fields

    def update(self, device_service, new_cfg: Dict[str, Any]):
        """Update device_service.cc and restart connections if needed."""
        self.log(f"🔧 Updating configuration for device {device_service.serial}")

        if not isinstance(new_cfg, dict):
            self.log("❌ Invalid config: expected a dict")
            return

        cc = device_service.cc
        prev = dict(cc)

        # Only allowed keys
        filtered = {k: v for k, v in new_cfg.items() if k in self._ALLOWED_KEYS}
        if not filtered:
            self.log("ℹ️ No applicable config changes.")
            return

        # Merge parcial 
        for k, v in filtered.items():
            if v is None and k in cc:
                del cc[k]
            elif v is not None:
                cc[k] = v

        # Detect changes
        changed_tcp    = any(prev.get(k) != cc.get(k) for k in ("host", "tcpPort", "slaveId"))
        changed_serial = any(prev.get(k) != cc.get(k) for k in ("serialPort", "baudrate", "slaveId"))
        changed_logo   = any(prev.get(k) != cc.get(k) for k in ("logoIp", "logoPort"))
        changed_mode   = prev.get("mode") != cc.get("mode")

        if changed_tcp and device_service.conns.tcp:
            self.log("Restarting Modbus TCP due to config change.")
            device_service.conns.tcp.update_config(
                cc.get("host"), cc.get("tcpPort"), cc.get("slaveId")
            )

        if changed_serial and device_service.conns.serial:
            self.log("Restarting Modbus Serial due to config change.")
            device_service.conns.serial.update_config(
                cc.get("serialPort"), cc.get("baudrate"), cc.get("slaveId")
            )

        if changed_logo and device_service.conns.logo:
            self.log("Restarting LOGO! due to config change.")
            device_service.conns.logo.update_config(
                cc.get("logoIp"), cc.get("logoPort")
            )

        if changed_mode:
            mode = cc.get("mode")
            self.log(f"Device mode changed to {mode}")
            if mode == "local":
                device_service.set_local()
            else:
                device_service.set_remote()

        if not any((changed_tcp, changed_serial, changed_logo, changed_mode)):
            self.log("No effective changes detected.")

        # Notificar actualización de campos
        self.update_fields(device_service)
