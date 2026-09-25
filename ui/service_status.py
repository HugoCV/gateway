"""Read systemd status without changing the service or requiring privileges."""
import subprocess
import sys


SERVICE_NAME = 'alrotek-gateway.service'


def read_service_status():
    if sys.platform != 'linux':
        return {'active': 'unavailable', 'enabled': 'unavailable'}
    states = {}
    for key, command in (('active', 'is-active'), ('enabled', 'is-enabled')):
        try:
            result = subprocess.run(
                ['systemctl', command, SERVICE_NAME], capture_output=True,
                text=True, timeout=2, check=False,
            )
            # Inactive and disabled states have nonzero exit codes. Do not turn
            # a bus/permission error or missing executable into "stopped".
            known = ({'active', 'inactive', 'failed', 'activating', 'deactivating',
                      'reloading', 'refreshing'} if key == 'active' else
                     {'enabled', 'enabled-runtime', 'disabled', 'masked',
                      'masked-runtime', 'static', 'indirect', 'generated',
                      'transient', 'alias', 'linked', 'linked-runtime', 'not-found'})
            value = result.stdout.strip()
            states[key] = value if value in known else 'unavailable'
        except (OSError, subprocess.TimeoutExpired):
            states[key] = 'unavailable'
    return states


def service_presentation(status, connected):
    active = status.get('active', 'checking')
    enabled = status.get('enabled', 'checking')
    active_labels = {
        'checking': 'Comprobando…', 'active': 'Activo', 'inactive': 'Detenido',
        'failed': 'Falló', 'activating': 'Iniciando…', 'deactivating': 'Deteniéndose…',
        'reloading': 'Recargando…', 'refreshing': 'Actualizando…',
        'unavailable': 'No se pudo consultar',
    }
    enabled_labels = {
        'checking': 'Comprobando…', 'enabled': 'Habilitado',
        'disabled': 'Deshabilitado · no arrancará automáticamente',
        'enabled-runtime': 'Temporal · no se conserva al reiniciar el equipo',
        'masked': 'Bloqueado', 'masked-runtime': 'Bloqueado temporalmente',
        'not-found': 'Servicio no instalado',
        'unavailable': 'No se pudo consultar',
    }
    if connected:
        runtime = 'Gateway conectado · responde a la ventana'
        hint = 'Puede cerrar esta ventana: el Gateway seguirá funcionando.'
    else:
        runtime = 'Gateway sin respuesta · reconexión automática'
        hint = 'La ventana no recibe datos del Gateway; no se puede confirmar su funcionamiento.'
    return {
        'service': 'Servicio del sistema: ' + active_labels.get(active, 'No se pudo consultar'),
        'startup': 'Inicio automático: ' + enabled_labels.get(enabled, f'No confirmado ({enabled})'),
        'runtime': runtime,
        'hint': hint,
        'service_color': '#a02020' if active in ('inactive', 'failed') else
                         '#207020' if active == 'active' else '#a05a00',
        'startup_color': '#207020' if enabled == 'enabled' else '#a05a00',
        'runtime_color': '#207020' if connected else '#a05a00',
    }
