import subprocess
import socket
import time
import os
import threading
from typing import Callable, Dict

class ConnectivityMonitor:
    """Monitors the internet connection and takes action to restore it if lost.
    Runs checks in a separate thread."""
    def __init__(
        self,
        log_callback: Callable[[str], None],
        status_callback: Callable[[bool, str], None] | None = None,
        wifi_interface: str = "wlan0",
        known_networks: Dict[str, str] = None,
        check_interval: int = 60,
        reboot_timeout: int = 3600
    ):
        self.log = log_callback
        self.wifi_interface = wifi_interface
        self.status_callback = status_callback
        self.known_networks = known_networks or {}
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
        """
        Reinicia la interfaz Wi-Fi usando NetworkManager (nmcli).
        Probado en reComputer R100x / Debian 12.
        """
        self.log("♻️ Reiniciando interfaz Wi-Fi mediante NetworkManager...")

        try:
            # 1️⃣ Apagar Wi-Fi
            subprocess.run(["sudo", "nmcli", "radio", "wifi", "off"], check=True)
            self.log("📴 Wi-Fi apagado.")
            time.sleep(3)

            # 2️⃣ Encender Wi-Fi
            subprocess.run(["sudo", "nmcli", "radio", "wifi", "on"], check=True)
            self.log("📶 Wi-Fi encendido.")
            time.sleep(5)

            # 3️⃣ Verificar estado actual
            result = subprocess.run(
                ["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device", "status"],
                capture_output=True, text=True
            )
            output = result.stdout.strip()
            for line in output.splitlines():
                if line.startswith("wlan0:"):
                    parts = line.split(":")
                    state = parts[1]
                    conn = parts[2] if len(parts) > 2 else ""
                    self.log(f"📡 wlan0 → {state} ({conn})")
                    if state == "connected":
                        self.log(f"✅ Wi-Fi reconectado correctamente a {conn}")
                        return
                    elif state == "disconnected":
                        self.log("⚠️ Wi-Fi encendido pero sin conexión, intentando reconectar...")
                        self._reconnect_known_networks()
                        return

            self.log("✅ Interfaz Wi-Fi reiniciada.")
        except subprocess.CalledProcessError as e:
            self.log(f"❌ Error reiniciando interfaz Wi-Fi: {e}")


    def _connect_to_known_networks(self) -> bool:
        """Tries to connect to one of the known Wi-Fi networks."""
        if not self.known_networks:
            return False
            
        for ssid, password in self.known_networks.items():
            self.log(f"📶 Intentando conectar a la red: {ssid}...")
            try:
                subprocess.run(["sudo", "wpa_cli", "-i", self.wifi_interface, "remove_network", "all"], stdout=subprocess.DEVNULL)
                net_id_output = subprocess.run(["sudo", "wpa_cli", "-i", self.wifi_interface, "add_network"], check=True, capture_output=True, text=True)
                net_id = net_id_output.stdout.strip()

                subprocess.run(["sudo", "wpa_cli", "-i", self.wifi_interface, "set_network", net_id, "ssid", f'"{ssid}"'], check=True)
                subprocess.run(["sudo", "wpa_cli", "-i", self.wifi_interface, "set_network", net_id, "psk", f'"{password}"'], check=True)
                subprocess.run(["sudo", "wpa_cli", "-i", self.wifi_interface, "enable_network", net_id], check=True)
                subprocess.run(["sudo", "wpa_cli", "-i", self.wifi_interface, "select_network", net_id], check=True)

                self.log(f"⏳ Esperando conexión a {ssid}...")
                time.sleep(15) # Give time for the connection to be established

                if self._is_connected():
                    self.status_callback and self.status_callback(True, ssid)
                    self.log(f"✅ Conectado a {ssid}.")
                    return True
            except subprocess.CalledProcessError as e:
                self.log(f"❌ Falló el comando de conexión a {ssid}: {e}")
        return False


    def _reconnect_known_networks(self):
        """Reconecta automáticamente a redes conocidas mediante nmcli."""
        for ssid, password in getattr(self, "known_networks", {}).items():
            try:
                self.log(f"🔄 Intentando reconectar a {ssid}...")
                subprocess.run(
                    ["sudo", "nmcli", "device", "wifi", "connect", ssid, "password", password],
                    check=True
                )
                self.log(f"✅ Reconectado a {ssid}")
                return True
            except subprocess.CalledProcessError:
                self.log(f"❌ No se pudo conectar a {ssid}")
        self.log("⚠️ Ninguna red conocida se pudo reconectar.")
        return False

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
                if not self._connect_to_known_networks():
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
        known_networks={"Chaves 5G": "qwerty25"}
    )
    monitor.start()
    
    try:
        # Keep the main script alive to see the monitoring
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor.stop()
        print("Programa terminado.")
