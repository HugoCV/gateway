# /opt/miapp/main.py
import os
import signal
import time
import argparse
import fcntl
import tempfile
from pathlib import Path
from threading import Event
import traceback

# Try to import the main logic controller
try:
    from application.app_controller import AppController
except Exception as e:
    print("[main] Error importando AppController:", e)
    traceback.print_exc()
    AppController = None


LOCK_PATH = (
    Path(tempfile.gettempdir()) / f"alrotek-gateway-{os.getuid()}.lock"
)


def acquire_runtime_lock():
    """Prevent GUI and headless modes from accessing the same ports together."""
    lock_file = LOCK_PATH.open("w")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return None
    lock_file.write(str(os.getpid()))
    lock_file.flush()
    return lock_file


def notify_already_running(mode):
    message = "Gateway ya está ejecutándose en otro proceso."
    print(f"[main] {message}")
    if mode != "gui":
        return
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(
            "Gateway en ejecución",
            "Gateway ya está activo en segundo plano. "
            "Detenga el servicio antes de abrir la interfaz operativa.",
        )
        root.destroy()
    except Exception:
        pass


def run_headless():
    """
    Run the app logic without a GUI for systemd usage.
    """
    stop_event = Event()

    def _graceful(signum, _):
        print(f"[headless] señal {signum} recibida, saliendo…")
        stop_event.set()

    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)

    if AppController is None:
        print("[headless] AppController no disponible, bucle dummy.")
        try:
            while not stop_event.is_set():
                time.sleep(0.5)
        finally:
            print("[headless] terminado.")
        return

    ctrl = AppController(window=None)
    try:
        ctrl.run(stop_event=stop_event)  # blocking method
    finally:
        if hasattr(ctrl, "close"):
            ctrl.close()
        print("[headless] shutdown completo.")


def run_gui():
    """
    Run the Tkinter UI.
    """
    from ui.main_window import MainWindow
    app = MainWindow()
    app.mainloop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["gui", "headless"],
        default=os.getenv("APP_MODE", "gui")  # default to GUI if not configured
    )
    args = parser.parse_args()

    runtime_lock = acquire_runtime_lock()
    if runtime_lock is None:
        notify_already_running(args.mode)
        return 1

    try:
        if args.mode == "gui":
            try:
                run_gui()
            except Exception as e:
                # Fallback to headless mode when DISPLAY is not available.
                if "no display name and no $display" in str(e).lower():
                    print("[main] No hay DISPLAY → cambiando a modo headless")
                    run_headless()
                else:
                    raise
        else:
            run_headless()
    finally:
        fcntl.flock(runtime_lock.fileno(), fcntl.LOCK_UN)
        runtime_lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
