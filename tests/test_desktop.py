"""Direct startup checks without MQTT, hardware, or a desktop session."""
import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from infrastructure import desktop


class DesktopTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.installed = self.root / 'installed' / 'gateway.json'
        for patcher in (patch.object(desktop, 'ROOT', self.root),
                        patch.object(desktop, 'INSTALLED_CONFIG', self.installed),
                        patch.dict(os.environ, {}, clear=True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_config_uses_existing_installed_identity_and_explicit_override(self):
        self.installed.parent.mkdir()
        self.installed.write_text('{"organizationId":"org","gatewayId":"gw"}')
        self.assertEqual(desktop.select_config(), self.installed)
        custom = self.root / 'custom.json'
        os.environ['GATEWAY_CONFIG_PATH'] = str(custom)
        self.assertEqual(desktop.select_config(), custom)
        self.assertIn('"gatewayId":"gw"', self.installed.read_text())

    def test_standalone_checkout_uses_project_identity(self):
        self.assertEqual(desktop.select_config(), self.root / 'data' / 'gateway.json')

    def test_running_motor_is_reused_and_window_opens(self):
        window = Mock()
        with patch.object(desktop, 'RuntimeClient') as client, \
                patch.object(desktop.subprocess, 'Popen') as spawn:
            self.assertEqual(desktop.run_desktop(window), 0)
        client.return_value.request.assert_called_once_with('status')
        spawn.assert_not_called()
        window.assert_called_once_with()

    def test_window_waits_for_motor_with_same_config_and_detached_process(self):
        events = []
        client = Mock()
        def status(*args):
            events.append('status')
            if len(events) < 3:
                raise FileNotFoundError()
            return {'ok': True}
        client.request.side_effect = status
        child = Mock()
        child.poll.return_value = None
        with patch.object(desktop, 'RuntimeClient', return_value=client), \
                patch.object(desktop.subprocess, 'Popen', return_value=child) as spawn, \
                patch.object(desktop.time, 'sleep'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(desktop.run_desktop(lambda: events.append('window')), 0)
        self.assertEqual(events, ['status', 'status', 'status', 'window'])
        args, kwargs = spawn.call_args
        self.assertEqual(args[0][-2:], ['--mode', 'headless'])
        self.assertTrue(kwargs['start_new_session'])
        self.assertEqual(kwargs['cwd'], self.root)
        self.assertEqual(kwargs['env']['GATEWAY_CONFIG_PATH'],
                         str(self.root / 'data' / 'gateway.json'))

    def test_motor_failure_is_reported_without_opening_empty_window(self):
        child = Mock(returncode=1)
        child.poll.return_value = 1
        window = Mock()
        errors = io.StringIO()
        with patch.object(desktop, 'RuntimeClient') as client, \
                patch.object(desktop.subprocess, 'Popen', return_value=child), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(errors):
            client.return_value.request.side_effect = FileNotFoundError()
            self.assertEqual(desktop.run_desktop(window), 1)
        window.assert_not_called()
        self.assertIn('código 1', errors.getvalue())
        self.assertIn('gateway.log', errors.getvalue())

    def test_permission_error_does_not_start_another_motor(self):
        with patch.object(desktop, 'RuntimeClient') as client, \
                patch.object(desktop.subprocess, 'Popen') as spawn, \
                contextlib.redirect_stderr(io.StringIO()):
            client.return_value.request.side_effect = PermissionError('denied')
            self.assertEqual(desktop.run_desktop(Mock()), 1)
        spawn.assert_not_called()

    def test_start_script_works_outside_project_directory_with_spaces(self):
        project = self.root / 'gateway project'
        python = project / 'venv' / 'bin' / 'python'
        python.parent.mkdir(parents=True)
        python.write_text('#!/bin/sh\nprintf "%s\\n" "$PWD" "$@"\n')
        python.chmod(0o755)
        source = Path(__file__).resolve().parents[1] / 'start.sh'
        shutil.copy2(source, project / 'start.sh')
        result = subprocess.run([str(project / 'start.sh')], cwd=self.root,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(),
                         [str(project), 'main.py', '--mode', 'desktop'])
