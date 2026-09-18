"""Exercise the local service/GUI boundary without MQTT, devices, or a desktop."""
import io
import errno
import importlib.util
import json
import os
import queue
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

import main
from infrastructure.runtime import RuntimeClient, RuntimeServer, RuntimeState, _RequestHandler
from ui.service_client import ServiceClient


class FakeController:
    def __init__(self):
        self.identity = {"organizationId": "org", "gatewayId": "gateway"}
        self.saved = None

    def runtime_snapshot(self):
        return {"gateway": self.identity.copy(), "devices": [{
            "name": "Pump", "serial": "001", "cc": {"serialPort": "/dev/ttyUSB0"},
            "connected": True, "connected_logo": False,
        }]}

    def save_gateway_identity(self, organization_id, gateway_id):
        self.saved = (organization_id, gateway_id)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        # Keep the Unix socket below the platform's path length limit.
        self.tmp = tempfile.TemporaryDirectory(dir="/tmp", prefix="gw-test-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "runtime" / "control.sock"
        self.controller = FakeController()
        self.state = RuntimeState()
        self.restarts = []
        self.server = RuntimeServer(self.controller, self.state,
                                    lambda: self.restarts.append(True), self.path)
        try:
            self.server.start()
        except PermissionError as error:
            if error.errno == errno.EPERM:
                self.skipTest("El entorno no permite crear sockets Unix")
            raise
        self.addCleanup(self.server.close)
        self.client = RuntimeClient(self.path)

    def wait_event(self, events, name):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            event, payload = events.get(timeout=max(0.01, deadline - time.monotonic()))
            if event == name:
                return payload
        self.fail(f"Missing event: {name}")

    def test_status_logs_permissions_and_two_independent_windows(self):
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        with patch("sys.stdout", new=io.StringIO()):
            self.state.log("Gateway conectado")
        self.state.connectivity(True, "Red local")
        first = self.client.request("status")
        second = RuntimeClient(self.path).request("status")
        self.assertEqual(first["devices"], second["devices"])
        self.assertEqual(first["connectivity"], {"connected": True, "network": "Red local"})
        self.assertEqual(first["logs"][0]["message"], "Gateway conectado")
        next_snapshot = self.client.request("status", instance=first["instance"], after=first["cursor"])
        self.assertEqual(next_snapshot["logs"], [])

    def test_closing_window_leaves_service_available(self):
        events = queue.Queue()
        window = ServiceClient(events, self.client, interval=0.02)
        self.addCleanup(window.close)
        self.wait_event(events, "runtime")
        window.close()
        window._thread.join(timeout=3)
        self.assertFalse(window._thread.is_alive())
        self.assertEqual(self.client.request("status")["gateway"], self.controller.identity)
        self.assertEqual(self.restarts, [])

    def test_window_waits_for_service_and_reconnects_after_restart(self):
        self.server.close()
        events = queue.Queue()
        window = ServiceClient(events, self.client, interval=0.02)
        self.addCleanup(window.close)
        self.wait_event(events, "service_unavailable")
        self.server.start()
        initial = self.wait_event(events, "runtime")
        self.server.close()
        self.wait_event(events, "service_unavailable")
        self.server.state = RuntimeState()
        with patch("sys.stdout", new=io.StringIO()):
            self.server.state.log("Servicio reiniciado")
        self.server.start()
        reconnected = self.wait_event(events, "runtime")
        self.assertNotEqual(initial["instance"], reconnected["instance"])
        self.assertEqual(reconnected["logs"][0]["message"], "Servicio reiniciado")

    def test_save_acknowledges_and_requests_service_restart(self):
        response = self.client.request("save_gateway", organizationId=" other-org ", gatewayId="other-gw")
        self.assertTrue(response["ok"])
        self.assertEqual(self.controller.saved, ("other-org", "other-gw"))
        # The callback is invoked immediately after flushing the response.
        deadline = time.monotonic() + 2
        while not self.restarts and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.restarts, [True])

    def test_invalid_commands_cannot_restart_or_stop_service(self):
        for action, values in [("stop", {}), ("exec", {"command": "reboot"}),
                               ("save_gateway", {"organizationId": "", "gatewayId": "gw"}),
                               ("save_gateway", {"organizationId": {}, "gatewayId": "gw"})]:
            with self.subTest(action=action, values=values):
                with self.assertRaises(ValueError):
                    self.client.request(action, **values)
        self.assertIsNone(self.controller.saved)
        self.assertEqual(self.restarts, [])
        self.assertTrue(self.client.request("status")["ok"])

    def test_malformed_request_does_not_break_later_connections(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.connect(str(self.path))
            connection.sendall(b"[]\n")
            self.assertFalse(json.loads(connection.recv(4096))["ok"])
        self.assertTrue(self.client.request("status")["ok"])

    def test_second_server_cannot_replace_active_socket(self):
        other = RuntimeServer(self.controller, self.state, lambda: None, self.path)
        with self.assertRaises(RuntimeError):
            other.start()
        self.assertTrue(self.client.request("status")["ok"])

    def test_unexpected_file_is_not_deleted(self):
        self.server.close()
        self.path.write_text("keep")
        with self.assertRaises(PermissionError):
            self.server.start()
        self.assertEqual(self.path.read_text(), "keep")

    def test_failed_save_keeps_service_running_without_restart(self):
        with patch.object(self.controller, "save_gateway_identity", side_effect=ValueError("ID fijado en .env")):
            with self.assertRaisesRegex(ValueError, "ID fijado"):
                self.client.request("save_gateway", organizationId="org", gatewayId="gw")
        self.assertEqual(self.restarts, [])
        self.assertTrue(self.client.request("status")["ok"])


class EntryPointTests(unittest.TestCase):
    def test_service_restart_closes_server_and_devices_before_returning(self):
        calls = []

        def controller_factory(**options):
            controller = Mock()
            controller.run.side_effect = lambda **_kwargs: options['restart_callback']()
            controller.close.side_effect = lambda: calls.append('devices closed')
            return controller

        server = Mock()
        server.start.side_effect = lambda: calls.append('server started')
        server.close.side_effect = lambda: calls.append('server closed')
        with patch.dict(sys.modules, {'application.app_controller': SimpleNamespace(AppController=controller_factory)}), \
                patch('infrastructure.runtime.RuntimeServer', return_value=server), \
                patch('main.signal.signal'):
            self.assertTrue(main.run_headless())
        self.assertEqual(calls, ['server started', 'server closed', 'devices closed'])

    def test_gui_does_not_acquire_service_lock_or_start_hardware(self):
        with patch.object(sys, "argv", ["main.py", "--mode", "gui"]), \
                patch.object(main, "run_gui") as gui, \
                patch.object(main, "acquire_runtime_lock") as lock, \
                patch.object(main, "run_headless") as headless:
            self.assertEqual(main.main(), 0)
        gui.assert_called_once_with()
        lock.assert_not_called()
        headless.assert_not_called()

    def test_second_hardware_process_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "runtime.lock"
            with patch.object(main, "LOCK_PATH", path):
                held = main.acquire_runtime_lock()
                self.assertIsNotNone(held)
                try:
                    result = subprocess.run([sys.executable, "-c", """
import main, sys
from pathlib import Path
main.LOCK_PATH = Path(sys.argv[1])
raise SystemExit(0 if main.acquire_runtime_lock() is None else 1)
""", str(path)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                finally:
                    held.close()
                released = main.acquire_runtime_lock()
                self.assertIsNotNone(released)
                released.close()

    def test_desktop_client_import_does_not_load_hardware_modules(self):
        result = subprocess.run([sys.executable, "-c", """
import sys
import main
import ui.service_client
assert 'application.app_controller' not in sys.modules
assert 'infrastructure.mqtt.mqtt_client' not in sys.modules
assert 'pymodbus' not in sys.modules
"""], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class MemoryConnection:
    """Exercise the real JSON client and handler without an OS socket."""
    def __init__(self, transport):
        self.transport = transport

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def settimeout(self, _timeout):
        pass

    def connect(self, _path):
        if not self.transport.available:
            raise ConnectionRefusedError("Servicio detenido")

    def sendall(self, payload):
        self.payload = payload

    def makefile(self, _mode):
        handler = object.__new__(_RequestHandler)
        handler.connection = self
        handler.rfile = io.BytesIO(self.payload)
        handler.wfile = io.BytesIO()
        handler.server = SimpleNamespace(runtime=self.transport.server)
        handler.handle()
        return io.BytesIO(handler.wfile.getvalue())


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.controller = FakeController()
        self.state = RuntimeState()
        self.restarts = []
        server = RuntimeServer(self.controller, self.state, lambda: self.restarts.append(True))
        self.transport = SimpleNamespace(server=server, available=True)
        patcher = patch("infrastructure.runtime.socket.socket",
                        side_effect=lambda *_args: MemoryConnection(self.transport))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = RuntimeClient()

    wait_event = ServiceTests.wait_event

    def start_window(self, events):
        window = ServiceClient(events, self.client, interval=0.01)
        def cleanup():
            window.close()
            window._thread.join(timeout=3)
        self.addCleanup(cleanup)
        return window

    def test_actual_client_and_handler_exchange_status_and_log_cursors(self):
        with patch("sys.stdout", new=io.StringIO()):
            self.state.log("Conectado")
        self.state.connectivity(True, "Red local")
        response = self.client.request("status")
        self.assertEqual(response["gateway"], self.controller.identity)
        self.assertTrue(response["devices"][0]["connected"])
        self.assertEqual(response["logs"][0]["message"], "Conectado")
        self.assertEqual(self.client.request("status", instance=response["instance"],
                                            after=response["cursor"])["logs"], [])

    def test_closing_one_window_keeps_service_and_other_window_working(self):
        first_events, second_events = queue.Queue(), queue.Queue()
        first = self.start_window(first_events)
        second = self.start_window(second_events)
        self.wait_event(first_events, "runtime")
        self.wait_event(second_events, "runtime")
        first.close()
        first._thread.join(timeout=2)
        self.assertFalse(first._thread.is_alive())
        self.assertTrue(second._thread.is_alive())
        self.assertTrue(self.client.request("status")["ok"])
        self.assertEqual(self.restarts, [])

    def test_window_waits_before_start_and_reconnects_with_new_log_cursor(self):
        self.transport.available = False
        events = queue.Queue()
        self.start_window(events)
        self.wait_event(events, "service_unavailable")
        self.transport.available = True
        initial = self.wait_event(events, "runtime")
        self.transport.available = False
        self.wait_event(events, "service_unavailable")
        new_state = RuntimeState()
        with patch("sys.stdout", new=io.StringIO()):
            new_state.log("Servicio reiniciado")
        self.transport.server.state = new_state
        self.transport.available = True
        latest = self.wait_event(events, "runtime")
        self.assertNotEqual(initial["instance"], latest["instance"])
        self.assertEqual(latest["logs"][0]["message"], "Servicio reiniciado")

    def test_save_restarts_service_and_keeps_window_polling(self):
        events = queue.Queue()
        window = self.start_window(events)
        self.wait_event(events, "runtime")
        window.save_gateway("new-org", "new-gateway")
        self.assertIsNone(self.wait_event(events, "save_result"))
        self.assertEqual(self.controller.saved, ("new-org", "new-gateway"))
        self.assertEqual(self.restarts, [True])
        self.assertTrue(window._thread.is_alive())

    def test_rejected_save_reports_error_without_restarting(self):
        with patch.object(self.controller, "save_gateway_identity", side_effect=ValueError("ID fijado en .env")):
            events = queue.Queue()
            window = self.start_window(events)
            self.wait_event(events, "runtime")
            window.save_gateway("new-org", "new-gateway")
            self.assertEqual(self.wait_event(events, "save_result"), "ID fijado en .env")
        self.assertEqual(self.restarts, [])

    def test_unsupported_and_invalid_requests_never_save_or_restart(self):
        for action, values in [("stop", {}), ("exec", {}),
                               ("status", {"after": -1}),
                               ("save_gateway", {"organizationId": "", "gatewayId": "g"}),
                               ("save_gateway", {"organizationId": "x\ny", "gatewayId": "g"})]:
            with self.assertRaises(ValueError):
                self.client.request(action, **values)
        self.assertEqual(self.restarts, [])
        self.assertIsNone(self.controller.saved)
        self.assertTrue(self.client.request("status")["ok"])

    def test_history_is_bounded_and_new_instance_ignores_old_cursor(self):
        with patch("sys.stdout", new=io.StringIO()):
            for index in range(300):
                self.state.log(str(index))
        result = self.client.request("status", instance="old-process", after=10000)
        self.assertEqual(len(result["logs"]), 250)
        self.assertEqual(result["logs"][0]["message"], "50")


class ControllerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.saved = Mock()
        modules = {
            'application.managers.gateway_manager': SimpleNamespace(GatewayManager=object),
            'application.managers.device_manager': SimpleNamespace(DeviceManager=object),
            'application.services.device_service': SimpleNamespace(DeviceService=object),
            'infrastructure.connectivity.connectivity': SimpleNamespace(ConnectivityMonitor=object),
            'infrastructure.mqtt.mqtt_client': SimpleNamespace(MqttClient=object),
            'infrastructure.config.loader': SimpleNamespace(get_gateway=lambda: {}, save_gateway=self.saved),
        }
        spec = importlib.util.spec_from_file_location('controller_test',
                    Path(__file__).resolve().parents[1] / 'application/app_controller.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)
        self.controller = object.__new__(module.AppController)
        self.controller.log = Mock()

    def test_snapshot_exposes_display_fields_without_credentials(self):
        self.controller.gateway_cfg = {'organizationId': 'org', 'gatewayId': 'gw', 'secret': 'hidden'}
        self.controller.devices = {'one': SimpleNamespace(
            name='Pump', serial='001', cc={'host': '192.0.2.1', 'password': 'hidden'},
            connected=True, connected_logo=False,
        )}
        result = self.controller.runtime_snapshot()
        self.assertEqual(result['gateway'], {'organizationId': 'org', 'gatewayId': 'gw'})
        self.assertEqual(result['devices'][0]['cc']['host'], '192.0.2.1')
        self.assertNotIn('hidden', json.dumps(result))

    def test_environment_identity_cannot_be_silently_overridden(self):
        with patch.dict(os.environ, {'GATEWAY_ID': 'fixed'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'GATEWAY_ID'):
                self.controller.save_gateway_identity('org', 'changed')
        self.saved.assert_not_called()
        with patch.dict(os.environ, {}, clear=True):
            self.controller.save_gateway_identity('org', 'changed')
        self.saved.assert_called_once_with({'organizationId': 'org', 'gatewayId': 'changed'})

    def test_connection_application_failure_is_logged(self):
        device = Mock()
        device.update_connection_config.side_effect = OSError('unavailable')
        self.controller.devices = {'one': device}
        with self.assertRaises(OSError):
            self.controller.on_receive_command('one', {
                'action': 'update-connections', 'params': {'host': '192.0.2.20'},
            })
        self.assertIn('Error aplicando conexión', self.controller.log.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
