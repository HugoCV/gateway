"""Exercise received configuration and connection history without hardware."""
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import main
from application.managers.device_manager import DeviceManager
from infrastructure.activity_log import create_activity_logger
from infrastructure.runtime import RuntimeState


ROOT = Path(__file__).resolve().parents[1]


class ActivityLogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'gateway.log'
        self.logger = create_activity_logger(self.path)
        self.addCleanup(lambda: [handler.close() for handler in self.logger.handlers])
        self.state = RuntimeState(log_writer=self.logger.info)
        output = patch('sys.stdout', new=io.StringIO())
        output.start()
        self.addCleanup(output.stop)

    def test_history_has_timestamp_and_survives_reopening(self):
        self.state.log('Conexión restablecida')
        another = create_activity_logger(self.path)
        try:
            another.info('Nuevo arranque')
        finally:
            for handler in another.handlers:
                handler.close()
        content = self.path.read_text()
        self.assertRegex(content, r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[+-]\d{4} INFO')
        self.assertIn('Conexión restablecida', content)
        self.assertIn('Nuevo arranque', content)

    def test_rotation_keeps_bounded_backups_and_latest_event(self):
        path = self.path.parent / 'rotate.log'
        logger = create_activity_logger(path, max_bytes=180, backups=2)
        try:
            for index in range(15):
                logger.info('Cambio de conexión número %s', index)
        finally:
            for handler in logger.handlers:
                handler.close()
        self.assertEqual(len(list(path.parent.glob('rotate.log*'))), 3)
        self.assertIn('número 14', path.read_text())
        self.assertNotIn('número 0\n', ''.join(p.read_text() for p in path.parent.glob('rotate.log*')))

    def test_received_configuration_is_logged_and_applied_without_credentials(self):
        mqtt, refresh = Mock(), Mock()
        manager = DeviceManager(mqtt, refresh, self.state.log)
        manager.load_devices()
        callback = mqtt.request_devices.call_args.args[0]
        device = {
            'serialNumber': 'pump-1', 'name': 'Bomba 1',
            'connections': [{'channelId': 'main', 'enabled': True,
                             'host': '192.0.2.10', 'port': 502,
                             'password': 'DO_NOT_LOG'}],
            'deviceProfileId': {'name': 'Perfil de bomba', 'version': 2,
                'channels': [{'id': 'main', 'protocol': 'modbus-tcp',
                              'items': [{'id': 'speed'}], 'password': 'DO_NOT_LOG'}]},
        }
        callback(None, None, SimpleNamespace(payload=json.dumps({'devices': [device]}).encode()))
        refresh.assert_called_once_with([device])
        content = self.path.read_text()
        for expected in ('Configuración recibida', 'pump-1', 'conexiones=1',
                         'Perfil de bomba', 'items=1', 'Configuración cargada'):
            self.assertIn(expected, content)
        self.assertNotIn('DO_NOT_LOG', content)

    def test_invalid_configuration_records_failure_without_applying(self):
        mqtt, refresh = Mock(), Mock()
        manager = DeviceManager(mqtt, refresh, self.state.log)
        manager.load_devices()
        callback = mqtt.request_devices.call_args.args[0]
        callback(None, None, SimpleNamespace(payload=b'{broken'))
        callback(None, None, SimpleNamespace(payload=b'{"devices": "invalid"}'))
        refresh.assert_not_called()
        self.assertEqual(self.path.read_text().count('No se pudo procesar'), 2)

    def test_connection_update_rebuilds_all_profile_channels(self):
        from application.services.device_service import DeviceService

        service = object.__new__(DeviceService)
        service._lock = __import__('threading').RLock()
        service.serial = 'pump-1'
        service.device = {}
        service.channels = {'old': Mock()}
        service.channel_status = {'old': True}
        service.stop = Mock()
        service._build_channels = Mock()
        service.start = Mock()
        service.log = self.state.log
        service.update_fields = Mock()
        connections = [{'channelId': 'main', 'host': '192.0.2.20', 'port': 502}]

        service.update_connections(connections)

        service.stop.assert_called_once()
        service._build_channels.assert_called_once()
        service.start.assert_called_once()
        self.assertEqual(service.device['connections'], connections)
        self.assertIn('Configuración de conexiones aplicada a pump-1', self.path.read_text())

    def test_headless_entrypoint_connects_runtime_messages_to_file(self):
        def run(log_writer):
            RuntimeState(log_writer=log_writer).log('Evento del motor')
            return False
        with patch.object(sys, 'argv', ['main.py', '--mode', 'headless']), \
                patch.object(main, 'LOCK_PATH', self.path.parent / 'motor.lock'), \
                patch.object(main, 'run_headless', side_effect=run), \
                patch('infrastructure.activity_log.create_activity_logger', return_value=self.logger):
            self.assertEqual(main.main(), 0)
        self.assertIn('Evento del motor', self.path.read_text())
        self.assertIn('Motor Gateway detenido', self.path.read_text())
