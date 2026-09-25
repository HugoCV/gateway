"""Validate and durably deduplicate equipment commands before touching hardware."""
import hashlib
import json
import time

from application.services.gateway_command_service import GatewayCommandService


class DeviceCommandService(GatewayCommandService):
    def __init__(self, path, organization_id, gateway_id, execute, publish, log=print):
        super().__init__(path, organization_id, gateway_id, None, publish, log)
        self.execute = execute
        # An interrupted write has an unknown outcome: never repeat it after reboot.
        for record in self.records.values():
            if record["status"] == "pending":
                record.update(status="failed", reason="execution_outcome_unknown", dirty=True)

    def receive(self, serial, command):
        if not isinstance(command, dict) or not isinstance(serial, str):
            return
        command_id = command.get("commandId")
        target = dict(self.target, deviceSerial=serial)
        if (not isinstance(command_id, str) or not 1 <= len(command_id) <= 128
                or command.get("target") != target):
            self.log("Comando de equipo rechazado: identificador o destino inválido.")
            return
        try:
            expires = self._timestamp(command.get("expiresAt"))
            issued = self._timestamp(command.get("issuedAt"))
            fingerprint = hashlib.sha256(json.dumps(command, sort_keys=True).encode()).hexdigest()
        except (ValueError, TypeError, AttributeError):
            self.log("Comando de equipo rechazado: fechas inválidas.")
            return
        with self.lock:
            if not self.ready:
                self.log("Comando de equipo rechazado: registro persistente no disponible.")
                return
            previous = self.records.get(command_id)
            if previous:
                if previous["fingerprint"] == fingerprint:
                    previous["dirty"] = previous["status"] != "pending"
                else:
                    self.log("Comando de equipo rechazado: identificador reutilizado.")
                return
            now = time.time()
            self.records = {key: value for key, value in self.records.items()
                            if value["expires"] + 86400 > now}
            if len(self.records) >= 1000:
                self.log("Comando de equipo rechazado: registro lleno.")
                return
            params = command.get("params")
            reason = None
            if type(command.get("version")) is not int or command["version"] != 1:
                reason = "unsupported_command_version"
            elif expires <= now or expires <= issued:
                reason = "command_expired"
            elif issued > now + 30 or expires - issued > 300:
                reason = "invalid_command_lifetime"
            elif command.get("action") not in ("device-command", "update-connections"):
                reason = "unsupported_device_action"
            elif not isinstance(params, dict):
                reason = "invalid_command_params"
            elif command["action"] == "device-command" and (
                    not isinstance(params.get("command"), str) or not params["command"].strip()
                    or len(params["command"]) > 128):
                reason = "invalid_command_params"
            record = {
                "fingerprint": fingerprint, "bootId": self.boot_id, "expires": expires,
                "status": "failed" if reason else "pending", "reason": reason,
                "dirty": bool(reason), "serial": serial,
                "params": params if isinstance(params, dict) else {},
                "action": command.get("action"),
            }
            self.records[command_id] = record
            try:
                self._save()  # Must succeed BEFORE any side effect.
            except OSError:
                self.ready = False
                self.log("No se pudo persistir el comando; equipo sin cambios.")
                return
            if reason:
                return
            try:
                result = self.execute(serial, command)
                record.update(status="success" if result is None else result["status"],
                              reason=None if result is None else result.get("reason"), dirty=True)
            except Exception:
                record.update(status="failed", reason="device_command_failed", dirty=True)
            try:
                self._save()
            except OSError:
                self.ready = False
                self.log("No se pudo guardar el resultado del comando de equipo.")

    def flush_results(self):
        with self.lock:
            if not self.ready or not any(record.get("dirty") for record in self.records.values()):
                return
            try:
                self._save()
                for command_id, record in self.records.items():
                    if not record.get("dirty") or record["status"] == "pending":
                        continue
                    if record.get("action") == "device-command":
                        params = record["params"]
                        acknowledged = self.publish(
                            device_serial=record["serial"], command_id=command_id,
                            status=record["status"], reason=record.get("reason"),
                            command_name=str(params.get("command", "")),
                            value=str(params.get("value", "on")), channel=params.get("channel"))
                        if not acknowledged:
                            continue
                    record["dirty"] = False
                    self._save()
            except Exception as error:
                self.log("No se pudo confirmar el comando de equipo: " + type(error).__name__)
