"""Private local connection between the Gateway service and desktop windows."""
import json
import os
import socket
import socketserver
import stat
import threading
import uuid
from collections import deque
from pathlib import Path


PROTOCOL_VERSION = 1
MAX_REQUEST = 8192
MAX_RESPONSE = 4 * 1024 * 1024


def socket_path():
    config = Path(os.environ.get(
        "GATEWAY_CONFIG_PATH",
        str(Path(__file__).resolve().parents[1] / "data" / "gateway.json"),
    ))
    return config.parent / "runtime" / "control.sock"


class RuntimeState:
    def __init__(self):
        self.instance = uuid.uuid4().hex
        self._lock = threading.Lock()
        self._logs = deque(maxlen=250)
        self._sequence = 0
        self._connectivity = {"connected": None, "network": "Verificando..."}

    def log(self, message):
        message = str(message)
        print(message, flush=True)
        with self._lock:
            self._sequence += 1
            self._logs.append({"id": self._sequence, "message": message[:2000]})

    def connectivity(self, connected, network):
        with self._lock:
            self._connectivity = {"connected": bool(connected), "network": str(network)}

    def snapshot(self, instance, after):
        with self._lock:
            cursor = after if instance == self.instance else 0
            return {
                "instance": self.instance,
                "cursor": self._sequence,
                "logs": [entry.copy() for entry in self._logs if entry["id"] > cursor],
                "connectivity": self._connectivity.copy(),
            }


class _RequestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(2)
        restart = False
        try:
            raw = self.rfile.readline(MAX_REQUEST + 1)
            if len(raw) > MAX_REQUEST or not raw.endswith(b"\n"):
                raise ValueError("Solicitud demasiado grande o incompleta.")
            request = json.loads(raw)
            response, restart = self.server.runtime.dispatch(request)
            payload = {"ok": True, "protocol": PROTOCOL_VERSION, **response}
        except (ValueError, TypeError, OSError) as error:
            payload = {"ok": False, "error": str(error)}
        except Exception:
            # Never expose tracebacks or configuration values to the client.
            payload = {"ok": False, "error": "No se pudo consultar el servicio."}
        try:
            self.wfile.write(json.dumps(payload).encode("utf-8") + b"\n")
            self.wfile.flush()
        except OSError:
            pass
        finally:
            # A saved configuration must take effect even if the window closes.
            if restart:
                self.server.runtime.restart()


class RuntimeServer:
    """The service owns this server; clients never acquire hardware resources."""
    def __init__(self, controller, state, restart, path=None):
        self.controller = controller
        self.state = state
        self.restart = restart
        self.path = Path(path) if path is not None else socket_path()
        self.server = None
        self.thread = None

    def start(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory = self.path.parent.lstat()
        if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid()
                or stat.S_IMODE(directory.st_mode) != 0o700):
            raise PermissionError("El directorio de comunicación debe ser privado (0700).")
        if self.path.exists() or self.path.is_symlink():
            existing = self.path.lstat()
            if not stat.S_ISSOCK(existing.st_mode) or existing.st_uid != os.getuid():
                raise PermissionError("La ruta del servicio contiene un archivo inesperado.")
            # Only remove an abandoned socket, never another running server.
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.settimeout(1)
                try:
                    probe.connect(str(self.path))
                except (ConnectionRefusedError, FileNotFoundError):
                    self.path.unlink(missing_ok=True)
                else:
                    raise RuntimeError("El servicio local ya está activo.")
        self.server = socketserver.UnixStreamServer(str(self.path), _RequestHandler)
        self.server.runtime = self
        self.path.chmod(0o600)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True,
        )
        self.thread.start()

    def close(self):
        if self.server is not None:
            if self.thread is not None:
                self.server.shutdown()
                self.thread.join(timeout=3)
            self.server.server_close()
            self.path.unlink(missing_ok=True)
            self.server = None
            self.thread = None

    def dispatch(self, request):
        if not isinstance(request, dict):
            raise ValueError("Solicitud inválida.")
        action = request.get("action")
        if action == "status":
            after = request.get("after", 0)
            if not isinstance(after, int) or after < 0:
                raise ValueError("Cursor inválido.")
            result = self.state.snapshot(request.get("instance"), after)
            result.update(self.controller.runtime_snapshot())
            return result, False
        if action == "save_gateway":
            org_id = request.get("organizationId")
            gateway_id = request.get("gatewayId")
            for value in (org_id, gateway_id):
                if (not isinstance(value, str) or not value.strip() or len(value) > 128
                        or any(ord(char) < 32 for char in value)):
                    raise ValueError("Indique Organization ID y Gateway ID válidos.")
            self.controller.save_gateway_identity(org_id.strip(), gateway_id.strip())
            return {}, True
        raise ValueError("Operación no disponible.")


class RuntimeClient:
    def __init__(self, path=None, timeout=2):
        self.path = Path(path) if path is not None else socket_path()
        self.timeout = timeout

    def request(self, action, **values):
        payload = json.dumps({"action": action, **values}).encode("utf-8") + b"\n"
        if len(payload) > MAX_REQUEST:
            raise ValueError("Solicitud demasiado grande.")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.timeout)
            connection.connect(str(self.path))
            connection.sendall(payload)
            with connection.makefile("rb") as stream:
                raw = stream.readline(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE or not raw.endswith(b"\n"):
            raise ValueError("Respuesta incompleta del servicio.")
        response = json.loads(raw)
        if not isinstance(response, dict):
            raise ValueError("Respuesta inválida del servicio.")
        if not response.get("ok"):
            raise ValueError(response.get("error", "Error del servicio."))
        if response.get("protocol") != PROTOCOL_VERSION:
            raise ValueError("Actualice Gateway y su interfaz a la misma versión.")
        return response
