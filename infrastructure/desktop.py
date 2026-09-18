"""Start or reuse the local runtime before opening its desktop window."""
import os
from pathlib import Path
import subprocess
import sys
import time

from infrastructure.runtime import RuntimeClient


ROOT = Path(__file__).resolve().parents[1]
INSTALLED_CONFIG = Path('/var/lib/alrotek-gateway/gateway.json')


def select_config():
    configured = os.environ.get('GATEWAY_CONFIG_PATH')
    if configured:
        path = Path(configured).expanduser().resolve()
    elif INSTALLED_CONFIG.exists():
        path = INSTALLED_CONFIG
    else:
        path = ROOT / 'data' / 'gateway.json'
    os.environ['GATEWAY_CONFIG_PATH'] = str(path)
    return path


def ensure_runtime(timeout=30):
    """The headless process owns the hardware lock, including concurrent starts."""
    config = select_config()
    client = RuntimeClient(timeout=1)
    try:
        client.request('status')
        return
    except (FileNotFoundError, ConnectionRefusedError):
        pass

    log_path = ROOT / 'gateway.log'
    # Keep raw output separate: a second writer would break activity log rotation.
    startup_path = ROOT / 'gateway-startup.log'
    print(f'Iniciando Gateway con configuración: {config}', flush=True)
    with startup_path.open('w', encoding='utf-8') as log:
        process = subprocess.Popen(
            [sys.executable, '-u', str(ROOT / 'main.py'), '--mode', 'headless'],
            cwd=ROOT, env=os.environ.copy(), stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            client.request('status')
            return
        except (FileNotFoundError, ConnectionRefusedError, TimeoutError):
            if process.poll() is not None:
                raise RuntimeError(
                    f'El motor Gateway terminó con código {process.returncode}. '
                    f'Revise {log_path} y {startup_path}. Si otro Gateway está activo, use su misma '
                    'cuenta y GATEWAY_CONFIG_PATH.'
                )
            time.sleep(0.2)
    raise RuntimeError(
        f'El motor todavía no responde. Revise {log_path}. '
        'No se inició otro motor adicional; puede volver a abrir ./start.sh.'
    )


def run_desktop(open_window):
    try:
        ensure_runtime()
    except (OSError, ValueError, RuntimeError) as error:
        print(f'No se pudo abrir Gateway: {error}', file=sys.stderr)
        return 1
    open_window()
    return 0
