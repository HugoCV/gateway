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
    Ejecuta la lógica sin GUI (para uso con systemd).
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

    ctrl = AppController(ui=None)  # sin GUI
    try:
        ctrl.run(stop_event=stop_event)  # método bloqueante
    finally:
        if hasattr(ctrl, "close"):
            ctrl.close()
        print("[headless] shutdown completo.")


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
