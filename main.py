# /opt/miapp/main.py
import os
import signal
import time
import argparse
from threading import Event
import traceback

# Intentar importar el controlador principal de la lógica
try:
    from application.app_controller import AppController
except Exception as e:
    print("[main] Error importando AppController:", e)
    traceback.print_exc()
    AppController = None


def run_headless():
    """
    Run the application without GUI (used for systemd / Docker).
    """
    stop_event = Event()

    def _graceful(signum, _):
        print(f"[headless] Signal {signum} received, shutting down…")
        stop_event.set()

    # Handle graceful shutdown signals (Docker, systemd, Ctrl+C)
    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)

    if AppController is None:
        print("[headless] AppController not available, running dummy loop.")
        try:
            while not stop_event.is_set():
                time.sleep(0.5)
        finally:
            print("[headless] Stopped.")
        return

    # Initialize controller (this should start background logic/threads)
    ctrl = AppController(window=None)

    # Keep process alive until a stop signal is received
    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    finally:
        print("[headless] Stopped. Calling controller shutdown...")
        if hasattr(ctrl, "shutdown"):
            ctrl.shutdown()




def run_gui():
    """
    Ejecuta la interfaz Tkinter.
    """
    from ui.main_window import MainWindow
    app = MainWindow()
    app.mainloop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["gui", "headless"],
        default=os.getenv("APP_MODE", "gui")  # por defecto GUI si no se define
    )
    args = parser.parse_args()

    if args.mode == "gui":
        try:
            run_gui()
        except Exception as e:
            # fallback: si no hay DISPLAY, intenta headless
            if "no display name and no $display" in str(e).lower():
                print("[main] No hay DISPLAY → cambiando a modo headless")
                run_headless()
            else:
                raise
    else:
        run_headless()


if __name__ == "__main__":
    main()
