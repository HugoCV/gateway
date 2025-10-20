# application/app_controller/connectivity_controller.py
from infrastructure.connectivity.connectivity import ConnectivityMonitor

class ConnectivityController:
    """
    Wraps ConnectivityMonitor and manages Wi-Fi networks and connectivity status.
    Keeps the gateway configuration and UI status in sync.
    """

    def __init__(self, gateway_cfg, log, status_callback):
        self.log = log
        self.status_callback = status_callback
        self.known_networks = gateway_cfg.get("known_networks", {"Chaves 5G": "qwerty25"})
        self.log(f"NETWORKS {self.known_networks}")
        self.monitor = None

    def start(self):
        """Start the connectivity monitor in its own thread."""
        if self.monitor and self.monitor.is_alive():
            self.log("⚠️ Connectivity monitor already running.")
            return

        self.monitor = ConnectivityMonitor(
            log_callback=self.log,
            known_networks=self.known_networks,
            status_callback=self.status_callback,
        )
        self.monitor.start()
        self.log("📡 Connectivity monitor started.")

    def stop(self):
        """Stop connectivity monitoring gracefully."""
        if self.monitor:
            try:
                self.monitor.stop()
                self.log("⏹️ Connectivity monitor stopped.")
            except Exception as e:
                self.log(f"⚠️ Error stopping connectivity monitor: {e}")

    def update_known_networks(self, networks: dict):
        """
        Update the list of Wi-Fi networks in real time and propagate to the monitor.
        """
        if not isinstance(networks, dict):
            self.log("⚠️ Invalid known networks format.")
            return

        self.known_networks = networks
        if self.monitor:
            self.monitor.known_networks = networks
        self.log("ℹ️ Known Wi-Fi networks updated.")
