"""Service status is independent of runtime reachability and never mutates systemd."""
import queue
import subprocess
import threading
import unittest
from unittest.mock import Mock, patch

from ui.service_client import ServiceClient
from ui.service_status import read_service_status, service_presentation


class SystemServiceTests(unittest.TestCase):
    def read_states(self, active, enabled):
        with patch('ui.service_status.sys.platform', 'linux'), \
                patch('ui.service_status.subprocess.run', side_effect=[active, enabled]) as run:
            result = read_service_status()
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ['systemctl', 'is-active', 'alrotek-gateway.service'],
            ['systemctl', 'is-enabled', 'alrotek-gateway.service'],
        ])
        for call in run.call_args_list:
            self.assertEqual(call.kwargs['timeout'], 2)
        return result

    def test_stopped_disabled_service_is_not_treated_as_query_failure(self):
        states = self.read_states(
            Mock(stdout='inactive\n', returncode=3),
            Mock(stdout='disabled\n', returncode=1),
        )
        self.assertEqual(states, {'active': 'inactive', 'enabled': 'disabled'})
        labels = service_presentation(states, False)
        self.assertIn('Detenido', labels['service'])
        self.assertIn('no arrancará automáticamente', labels['startup'])
        self.assertNotIn('seguirá funcionando', labels['hint'])

    def test_active_does_not_claim_runtime_is_responding(self):
        states = self.read_states(Mock(stdout='active\n'), Mock(stdout='enabled\n'))
        labels = service_presentation(states, False)
        self.assertIn('Activo', labels['service'])
        self.assertIn('sin respuesta', labels['runtime'])
        self.assertIn('no se puede confirmar', labels['hint'])

    def test_connected_runtime_does_not_hide_disabled_startup(self):
        labels = service_presentation({'active': 'active', 'enabled': 'disabled'}, True)
        self.assertIn('conectado', labels['runtime'])
        self.assertIn('Deshabilitado', labels['startup'])

    def test_failed_service_remains_distinct_from_stopped(self):
        states = self.read_states(Mock(stdout='failed\n', returncode=3), Mock(stdout='enabled\n'))
        self.assertIn('Falló', service_presentation(states, False)['service'])

    def test_runtime_can_run_independently_of_systemd(self):
        labels = service_presentation({'active': 'inactive', 'enabled': 'disabled'}, True)
        self.assertIn('Detenido', labels['service'])
        self.assertIn('conectado', labels['runtime'])

    def test_missing_systemctl_or_timeout_never_means_inactive(self):
        for error in (FileNotFoundError(), PermissionError(),
                      subprocess.TimeoutExpired('systemctl', 2)):
            with self.subTest(error=type(error).__name__):
                states = self.read_states(error, error)
                self.assertEqual(states, {'active': 'unavailable', 'enabled': 'unavailable'})

    def test_bus_failure_output_never_means_disabled(self):
        states = self.read_states(Mock(stdout='', returncode=1), Mock(stdout='', returncode=1))
        self.assertEqual(states, {'active': 'unavailable', 'enabled': 'unavailable'})

    def test_temporary_enablement_does_not_promise_boot_start(self):
        labels = service_presentation({'active': 'active', 'enabled': 'enabled-runtime'}, True)
        self.assertIn('no se conserva al reiniciar', labels['startup'])

    def test_non_linux_does_not_launch_systemctl(self):
        with patch('ui.service_status.sys.platform', 'darwin'), \
                patch('ui.service_status.subprocess.run') as run:
            self.assertEqual(read_service_status(),
                             {'active': 'unavailable', 'enabled': 'unavailable'})
        run.assert_not_called()

    def test_status_polling_continues_when_runtime_is_unavailable(self):
        events = queue.Queue()
        runtime = Mock()
        runtime.request.side_effect = FileNotFoundError()
        poll_threads = []
        def read_status():
            poll_threads.append(threading.get_ident())
            return {'active': 'inactive', 'enabled': 'disabled'}
        with patch('ui.service_client.read_service_status', side_effect=read_status), \
                patch('ui.service_client.time.monotonic', side_effect=[0, 0, 6, 6, 12, 12]):
            client = ServiceClient(events, runtime, interval=0.01)
            try:
                statuses = []
                while len(statuses) < 2:
                    event, data = events.get(timeout=2)
                    if event == 'system_service':
                        statuses.append(data)
            finally:
                client.close()
                client._thread.join(timeout=3)
        self.assertEqual(len(statuses), 2)
        self.assertTrue(all(ident != threading.get_ident() for ident in poll_threads))


if __name__ == '__main__':
    unittest.main()
