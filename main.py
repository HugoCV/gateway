"""Run the hardware service or its independent desktop client."""
import argparse
import fcntl
import os
import signal
import sys
import tempfile
from pathlib import Path
from threading import Event


SERVICE_UI_PROTOCOL = 1

LOCK_PATH = Path(tempfile.gettempdir()) / f"alrotek-gateway-{os.getuid()}.lock"


def acquire_runtime_lock():
    """Only the background service may own the hardware runtime."""
    lock_file = LOCK_PATH.open("a+")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return None
    lock_file.seek(0)
    lock_file.truncate()
    lock_file.write(str(os.getpid()))
    lock_file.flush()
    return lock_file


def run_headless():
    # Desktop clients never import MQTT, Modbus, or their configuration.
    from application.app_controller import AppController
    from infrastructure.runtime import RuntimeServer, RuntimeState

    stop_event = Event()
    restart_event = Event()
    state = RuntimeState()

    def request_restart():
        restart_event.set()
        stop_event.set()

    def graceful_stop(signum, _frame):
        state.log(f"[servicio] Señal {signum}; cerrando conexiones…")
        stop_event.set()

    signal.signal(signal.SIGTERM, graceful_stop)
    signal.signal(signal.SIGINT, graceful_stop)
    controller = AppController(log_callback=state.log,
                               status_callback=state.connectivity,
                               restart_callback=request_restart)
    server = RuntimeServer(controller, state, request_restart)
    try:
        server.start()
        controller.run(stop_event=stop_event)
    finally:
        server.close()
        controller.close()
    return restart_event.is_set()


def run_gui():
    from ui.main_window import MainWindow
    MainWindow().mainloop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["gui", "headless", "desktop"],
                        default=os.getenv("APP_MODE", "gui"))
    args = parser.parse_args()
    if args.mode == "desktop":
        from infrastructure.desktop import run_desktop
        return run_desktop(run_gui)
    if args.mode == "gui":
        # The window can be opened before the service and while it is restarting.
        run_gui()
        return 0

    runtime_lock = acquire_runtime_lock()
    if runtime_lock is None:
        print("Gateway ya está ejecutándose en otro proceso.")
        return 1
    try:
        restart = run_headless()
    finally:
        fcntl.flock(runtime_lock.fileno(), fcntl.LOCK_UN)
        runtime_lock.close()
    if restart:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
