import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from application.services.device_command_service import DeviceCommandService


class DeviceCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'commands.json'
        self.execute = Mock(return_value={'status': 'success'})
        self.publish = Mock(return_value=True)
        now = datetime.now(timezone.utc)
        self.command = {'version': 1, 'commandId': 'one', 'issuedAt': now.isoformat(),
                        'expiresAt': (now + timedelta(seconds=60)).isoformat(),
                        'target': {'organizationId': 'org', 'gatewayId': 'gw', 'deviceSerial': 'pump'},
                        'action': 'device-command', 'params': {'command': 'restart'}}
        self.service = self.make_service()

    def make_service(self):
        return DeviceCommandService(self.path, 'org', 'gw', self.execute, self.publish, Mock())

    def test_valid_command_executes_once_including_after_process_restart(self):
        self.service.receive('pump', self.command)
        self.service.flush_results()
        self.service.receive('pump', self.command)
        self.make_service().receive('pump', self.command)
        self.execute.assert_called_once()
        self.assertEqual(self.publish.call_args.kwargs['status'], 'success')

    def test_invalid_envelopes_never_touch_hardware(self):
        for changes in [
            {'expiresAt': '2000-01-01T00:00:00Z'}, {'version': 2},
            {'target': {'organizationId': 'other'}}, {'commandId': None},
            {'issuedAt': None}, {'params': []}, {'params': {}}, {'action': 'unknown'},
            {'issuedAt': '2099-01-01T00:00:00Z', 'expiresAt': '2099-01-01T00:01:00Z'},
        ]:
            with self.subTest(changes=changes):
                command = dict(self.command, **changes)
                self.service.receive('pump', command)
        self.execute.assert_not_called()

    def test_reused_id_cannot_change_action(self):
        self.service.receive('pump', self.command)
        changed = copy.deepcopy(self.command)
        changed['params']['command'] = 'turnOn'
        self.service.receive('pump', changed)
        self.execute.assert_called_once()

    def test_storage_failure_and_corruption_fail_closed(self):
        with patch.object(self.service, '_save', side_effect=OSError('disk')):
            self.service.receive('pump', self.command)
        self.execute.assert_not_called()
        self.path.write_text('corrupt')
        self.make_service().receive('pump', self.command)
        self.execute.assert_not_called()

    def test_interrupted_execution_is_not_repeated(self):
        with patch.object(self.service, 'execute', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.service.receive('pump', self.command)
        restarted = self.make_service()
        restarted.receive('pump', self.command)
        restarted.flush_results()
        self.execute.assert_not_called()
        self.assertEqual(self.publish.call_args.kwargs['reason'], 'execution_outcome_unknown')

    def test_publish_failure_keeps_result_for_reconnect(self):
        self.service.receive('pump', self.command)
        self.publish.return_value = False
        self.service.flush_results()
        self.publish.return_value = True
        self.make_service().flush_results()
        self.assertEqual(self.publish.call_count, 2)
        self.execute.assert_called_once()


if __name__ == '__main__':
    unittest.main()
