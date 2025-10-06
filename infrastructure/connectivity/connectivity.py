import subprocess
import socket
import time
import os
import threading
from typing import Callable, Dict

class ConnectivityMonitor:
    """
    Monitorea la conexión a Internet y toma acciones para restablecerla si se pierde.
    Ejecuta las verificaciones en un hilo separado.
    """
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
        """Inicia el hilo de monitoreo."""
        if self._thread and self._thread.is_alive():
            self.log("⚠️ ConnectivityMonitor ya está corriendo.")
            return
        
        self.log("▶️ Iniciando monitor de conectividad.")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_monitor, daemon=True)
        self._thread.start()

    def stop(self):
        """Detiene el hilo de monitoreo."""
        self.log("⏹️ Deteniendo monitor de conectividad.")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _is_connected(self) -> bool:
        """Verifica si hay conexión a Internet."""
        try:
            # Conectar al DNS de Google como prueba
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return True
        except OSError:
            return False

    def _get_current_ssid(self) -> str:
        """Obtiene el SSID de la red Wi-Fi actual."""
        try:
            # Usamos iwgetid para obtener el SSID de la interfaz
            result = subprocess.run(["iwgetid", "-r", self.wifi_interface], capture_output=True, text=True, check=True)
            ssid = result.stdout.strip()
            return ssid if ssid else "Desconocida"
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Si el comando falla o no se encuentra, no estamos conectados a una red Wi-Fi
            return "Ninguna"

    def _unblock_wifi_rfkill(self):
        """Desbloquea el Wi-Fi si está bloqueado por software."""
        try:
            rfkill_output = subprocess.run(["rfkill", "list", "all"], capture_output=True, text=True)
            if "Soft blocked: yes" in rfkill_output.stdout:
                self.log("🔓 Desbloqueando Wi-Fi (rfkill)...")
                subprocess.run(["sudo", "rfkill", "unblock", "wifi"], check=True)
                time.sleep(1)
        except Exception as e:
            self.log(f"⚠️ Error en rfkill: {e}")

    def _restart_wifi_interface(self):
        """Reinicia la interfaz de red especificada."""
        self.log(f"♻️ Reiniciando interfaz {self.wifi_interface}...")
        self._unblock_wifi_rfkill()
        try:
            subprocess.run(["sudo", "ip", "link", "set", self.wifi_interface, "down"], check=True)
            time.sleep(3)
            subprocess.run(["sudo", "ip", "link", "set", self.wifi_interface, "up"], check=True)
            self.log("✅ Interfaz reiniciada.")
        except subprocess.CalledProcessError as e:
            self.log(f"❌ Error reiniciando interfaz: {e}")

    def _connect_to_known_networks(self) -> bool:
        """Intenta conectarse a una de las redes Wi-Fi conocidas."""
        if not self.known_networks:
            return False
            
        for ssid, password in self.known_networks.items():
            self.log(f"📶 Intentando conectar a la red: {ssid}...")
            try:
                # Limpia redes anteriores y añade una nueva configuración
                subprocess.run(["sudo", "wpa_cli", "-i", self.wifi_interface, "remove_network", "all"], stdout=subprocess.DEVNULL)
                net_id_output = subprocess.run(["sudo", "wpa_cli", "-i", self.wifi_interface, "add_network"], check=True, capture_output=True, text=True)
                net_id = net_id_output.stdout.strip()

                subprocess.run(["sudo", "wpa_cli", "-i", self.wifi_interface, "set_network", net_id, "ssid", f'"{ssid}"'], check=True)
                subprocess.run(["sudo", "wpa_cli", "-i", self.wifi_interface, "set_network", net_id, "psk", f'"{password}"'], check=True)
                subprocess.run(["sudo", "wpa_cli", "-i", self.wifi_interface, "enable_network", net_id], check=True)
                subprocess.run(["sudo", "wpa_cli", "-i", self.wifi_interface, "select_network", net_id], check=True)

                self.log(f"⏳ Esperando conexión a {ssid}...")
                time.sleep(15) # Dar tiempo a que se establezca la conexión

                if self._is_connected():
                    self.log(f"✅ Conectado exitosamente a {ssid}.")
                    return True
            except subprocess.CalledProcessError as e:
                self.log(f"❌ Falló el comando de conexión a {ssid}: {e}")
        return False

    def _restart_device(self):
        """Reinicia el sistema operativo."""
        self.log(f"🔁 Reiniciando equipo (más de {self.reboot_timeout}s sin conexión).")
        os.system("sudo reboot")

    def _run_monitor(self):
        """Bucle principal de monitoreo."""
        while not self._stop_event.is_set():
            if self._is_connected():
                current_ssid = self._get_current_ssid()
                # Notificar solo si el estado o el SSID ha cambiado
                if self._last_status is not True or self._last_ssid != current_ssid:
                    self.log("✅ Conexión a Internet activa.")
                    if self.status_callback:
                        self.status_callback(True, current_ssid)
                    self._last_status = True
                    self._last_ssid = current_ssid
                if self.disconnected_time > 0:
                    self.disconnected_time = 0 # Reiniciar contador solo si venimos de un estado desconectado
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
                    break # Salir del bucle después de ordenar el reinicio
            
            self._stop_event.wait(self.check_interval)

if __name__ == '__main__':
    # Ejemplo de uso
    def simple_logger(message):
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")
        
    monitor = ConnectivityMonitor(
        log_callback=simple_logger,
        known_networks={"Chaves 5G": "qwerty25"}
    )
    monitor.start()
    
    try:
        # Mantener el script principal vivo para ver el monitoreo
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor.stop()
        print("Programa terminado.")
