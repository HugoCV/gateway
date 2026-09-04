from __future__ import annotations

import subprocess
import socket
import time
import os
import threading
from typing import Callable

class ConnectivityMonitor:
    """Monitors the internet connection and takes action to restore it if lost.
    Runs checks in a separate thread."""
    def __init__(
        self,
        log_callback: Callable[[str], None],
        status_callback: Callable[[bool, str], None] | None = None,
        wifi_interface: str = "wlan0",
        check_interval: int = 60,
        reboot_timeout: int = 3600
    ):
        self.log = log_callback
        self.wifi_interface = wifi_interface
        self.status_callback = status_callback
        self.check_interval = check_interval
        self.reboot_timeout = reboot_timeout
        
        self.disconnected_time = 0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_status: bool | None = None
        self._last_ssid: str | None = None


    def start(self):
        """Starts the monitoring thread."""
        if self._thread and self._thread.is_alive():
            self.log("⚠️ ConnectivityMonitor ya está corriendo.")
            return
        
        self.log("▶️ Iniciando monitor de conectividad.")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_monitor, daemon=True)
        self._thread.start()

    def stop(self):
        """Stops the monitoring thread."""
        self.log("⏹️ Deteniendo monitor de conectividad.")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _is_connected(self) -> bool:
        """Checks if there is an internet connection."""
        try:
            # Connect to Google's DNS as a test
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return True
        except OSError:
            return False

    def _get_current_ssid(self) -> str:
        """Gets the SSID of the current Wi-Fi network."""
        try:
            # We use iwgetid to get the SSID of the interface
            result = subprocess.run(["iwgetid", "-r", self.wifi_interface], capture_output=True, text=True, check=True)
            ssid = result.stdout.strip()
            return ssid if ssid else "Desconocida"
        except (subprocess.CalledProcessError, FileNotFoundError):
            # If the command fails or is not found, we are not connected to a Wi-Fi network
            return "Ninguna"

    def _unblock_wifi_rfkill(self):
        try:
            rfkill_output = subprocess.run(["rfkill", "list", "all"], capture_output=True, text=True)
            if "Soft blocked: yes" in rfkill_output.stdout:
                self.log("🔓 Desbloqueando Wi-Fi (rfkill)...")
                subprocess.run(["sudo", "rfkill", "unblock", "wifi"], check=True)
                time.sleep(1)
        except Exception as e:
            self.log(f"⚠️ Error en rfkill: {e}")

    def _restart_wifi_interface(self):
        """Restarts the specified network interface."""
        self.log(f"♻️ Reiniciando interfaz {self.wifi_interface}...")
        self._unblock_wifi_rfkill()
        try:
            subprocess.run(["sudo", "ip", "link", "set", self.wifi_interface, "down"], check=True)
            time.sleep(3)
            subprocess.run(["sudo", "ip", "link", "set", self.wifi_interface, "up"], check=True)
            self.log("✅ Interfaz reiniciada.")
        except subprocess.CalledProcessError as e:
            self.log(f"❌ Error reiniciando interfaz: {e}")

    def _restart_device(self):
        """Reboots the operating system."""
        self.log(f"🔁 Reiniciando equipo (más de {self.reboot_timeout}s sin conexión).")
        os.system("sudo reboot")

    def _run_monitor(self):
        """Main monitoring loop."""
        while not self._stop_event.is_set():
            if self._is_connected():
                current_ssid = self._get_current_ssid()
                # Notify only if the status or SSID has changed
                if self._last_status is not True or self._last_ssid != current_ssid:
                    self.log("✅ Conexión a Internet activa.")
                    if self.status_callback:
                        self.status_callback(True, current_ssid)
                    self._last_status = True
                    self._last_ssid = current_ssid
                if self.disconnected_time > 0:
                    self.disconnected_time = 0 # Reset counter only if coming from a disconnected state
            else:
                if self._last_status is not False:
                    self.log("⚠️ Sin conexión a Internet.")
                    if self.status_callback:
                        self.status_callback(False, "Ninguna")
                    self._last_status = False
                    self._last_ssid = "Ninguna"

                self.disconnected_time += self.check_interval
                self._restart_wifi_interface()
                
                if self.disconnected_time >= self.reboot_timeout:
                    self._restart_device()
                    break # Exit the loop after ordering the reboot
            
            self._stop_event.wait(self.check_interval)

if __name__ == '__main__':
    # Example usage
    def simple_logger(message):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")
        
    monitor = ConnectivityMonitor(
        log_callback=simple_logger,
    )
    monitor.start()
    
    try:
        # Keep the main script alive to see the monitoring
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor.stop()
        print("Programa terminado.")
