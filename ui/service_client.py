"""Poll the service off the Tk thread, reconnecting across service restarts."""
import queue
import threading

from infrastructure.runtime import RuntimeClient


class ServiceClient:
    def __init__(self, events, client=None, interval=1):
        self.events = events
        self.client = client or RuntimeClient()
        self.interval = interval
        self._stop = threading.Event()
        self._commands = queue.Queue(maxsize=1)
        self._instance = None
        self._cursor = 0
        self._connected = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def save_gateway(self, organization_id, gateway_id):
        self._commands.put_nowait((organization_id, gateway_id))

    def close(self):
        # Closing a window only stops its own polling; the service stays alive.
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                organization_id, gateway_id = self._commands.get_nowait()
            except queue.Empty:
                pass
            else:
                try:
                    self.client.request("save_gateway", organizationId=organization_id,
                                        gatewayId=gateway_id)
                except (OSError, ValueError) as error:
                    self.events.put(("save_result", str(error)))
                else:
                    self.events.put(("save_result", None))
            try:
                snapshot = self.client.request("status", instance=self._instance,
                                               after=self._cursor)
                self._instance = snapshot["instance"]
                self._cursor = snapshot["cursor"]
                self._connected = True
                self.events.put(("runtime", snapshot))
            except (OSError, ValueError, KeyError) as error:
                if self._connected is not False:
                    self.events.put(("service_unavailable", str(error)))
                self._connected = False
            self._stop.wait(self.interval)
