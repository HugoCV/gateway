"""Durable restart journal. A reconnect in the same process is NOT a restart."""
import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path


class GatewayCommandService:
    def __init__(self, path, organization_id, gateway_id, restart, publish, log=print):
        self.path = Path(path)
        self.target = {"organizationId": str(organization_id), "gatewayId": str(gateway_id)}
        self.restart = restart
        self.publish = publish
        self.log = log
        self.boot_id = str(uuid.uuid4())
        self.lock = threading.RLock()
        self.records = {}
        self.ready = True
        try:
            if self.path.exists():
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                if saved.get("target") != self.target or saved.get("version") != 1:
                    raise ValueError("Journal identity/version mismatch")
                records = saved["commands"]
                if not isinstance(records, dict) or len(records) > 1000:
                    raise ValueError("Invalid journal")
                for key, record in records.items():
                    if (not isinstance(key, str) or not isinstance(record, dict)
                            or record.get("status") not in ("pending", "success", "failed")
                            or not isinstance(record.get("expires"), (int, float))
                            or not isinstance(record.get("bootId"), str)
                            or not isinstance(record.get("fingerprint"), str)):
                        raise ValueError("Invalid journal entry")
                self.records = records
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            self.ready = False
            self.log("No se pudo leer el registro de comandos; reinicios remotos deshabilitados.")

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".gateway-command-", dir=str(self.path.parent))
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump({"version": 1, "target": self.target, "commands": self.records}, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
            directory = os.open(str(self.path.parent), os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _timestamp(value):
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError("Timezone required")
        return date.timestamp()

    def receive(self, command):
        if not isinstance(command, dict):
            return
        command_id = command.get("commandId")
        if (not isinstance(command_id, str) or not 1 <= len(command_id) <= 128
                or command.get("target") != self.target):
            self.log("Comando de gateway rechazado: identificador o destino inválido.")
            return
        try:
            expires = self._timestamp(command.get("expiresAt"))
            issued = self._timestamp(command.get("issuedAt"))
            fingerprint = hashlib.sha256(json.dumps(command, sort_keys=True).encode()).hexdigest()
        except (ValueError, TypeError, AttributeError):
            self.log("Comando de gateway rechazado: sobre inválido.")
            return

        with self.lock:
            if not self.ready:
                return  # Fail closed: never restart without durable deduplication.
            previous = self.records.get(command_id)
            if previous:
                if previous["fingerprint"] != fingerprint:
                    self.log("Comando de gateway rechazado: identificador reutilizado.")
                    return
                previous["dirty"] = previous["status"] != "pending"
                return  # Same command never executes twice, even after a process restart.
            now = time.time()
            self.records = {key: record for key, record in self.records.items()
                            if record["expires"] + 86400 > now or record["status"] == "pending"}
            if len(self.records) >= 1000:
                self.log("Registro de comandos lleno; reinicio rechazado.")
                return
            reason = None
            if type(command.get("version")) is not int or command["version"] != 1:
                reason = "unsupported_command_version"
            elif expires <= now or expires <= issued:
                reason = "command_expired"
            elif issued > now + 30:
                reason = "command_issued_in_future"
            elif command.get("action") != "restart":
                reason = "unsupported_gateway_command"
            elif any(record["status"] == "pending" for record in self.records.values()):
                reason = "gateway_command_in_progress"
            self.records[command_id] = {
                "fingerprint": fingerprint, "bootId": self.boot_id, "expires": expires,
                "status": "failed" if reason else "pending", "reason": reason, "dirty": bool(reason),
            }
            try:
                self._save()
            except OSError:
                self.ready = False
                self.log("No se pudo persistir el comando; no se reiniciará el gateway.")
                return
        if reason:
            return
        try:
            self.restart()
        except Exception:
            with self.lock:
                self.records[command_id].update(status="failed", reason="gateway_restart_failed", dirty=True)
                try:
                    self._save()
                except OSError:
                    self.ready = False
                    self.log("No se pudo guardar el error de reinicio.")

    def flush_results(self):
        """Called by MQTT heartbeat worker, never its network callback thread.

        A new process with a connected MQTT session confirms recovery. Completed
        results remain in the outbox until the broker acknowledges them.
        """
        with self.lock:
            if not self.ready:
                return
            try:
                changed = False
                for record in self.records.values():
                    if record["status"] == "pending" and record["bootId"] != self.boot_id:
                        record.update(status="success", reason=None, dirty=True)
                        changed = True
                if changed:
                    self._save()  # Persist success before publishing it.
                for command_id, record in self.records.items():
                    if record.get("dirty") and record["status"] != "pending":
                        acknowledged = self.publish({"commandId": command_id,
                            "status": record["status"], "reason": record.get("reason")})
                        if acknowledged:
                            record["dirty"] = False
                            self._save()
            except Exception as error:
                self.log("No se pudo confirmar el comando; se reintentará: " + type(error).__name__)
