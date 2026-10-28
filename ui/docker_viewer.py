"""Read-only desktop transport for a Gateway already running in Docker."""
import json
import re
import subprocess

from infrastructure.runtime import PROTOCOL_VERSION


_STATUS_SCRIPT = """
import json
import sys
from infrastructure.runtime import RuntimeClient
request = json.loads(sys.stdin.readline())
response = RuntimeClient().request(
    'status', instance=request.get('instance'), after=request.get('after', 0))
sys.stdout.write(json.dumps(response) + '\\n')
"""


class DockerRuntimeClient:
    """Query status through docker exec; never forward service-changing actions."""

    def __init__(self, container, timeout=5):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", container):
            raise ValueError("Nombre de contenedor inválido.")
        self.container = container
        self.timeout = timeout

    def request(self, action, **values):
        if action != "status":
            raise ValueError("El visor de Docker es de solo lectura.")
        payload = json.dumps({"instance": values.get("instance"),
                              "after": values.get("after", 0)}) + "\n"
        try:
            result = subprocess.run(
                ["docker", "exec", "-i", self.container, "python", "-c", _STATUS_SCRIPT],
                input=payload, text=True, capture_output=True, timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise OSError("No se pudo consultar Docker.") from error
        if result.returncode != 0:
            raise OSError("El contenedor no responde. Comprueba que siga activo.")
        try:
            response = json.loads(result.stdout)
        except (TypeError, ValueError) as error:
            raise ValueError("Respuesta inválida del gateway en Docker.") from error
        if not isinstance(response, dict) or not response.get("ok"):
            raise ValueError("El gateway no pudo entregar su estado.")
        if response.get("protocol") != PROTOCOL_VERSION:
            raise ValueError("La interfaz y el gateway usan versiones incompatibles.")
        return response
