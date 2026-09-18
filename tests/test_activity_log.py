"""Exercise received configuration and connection history without hardware."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from threading import RLock
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
            'connectionConfig': {'host': '192.0.2.10', 'tcpPort': 502,
                                 'password': 'DO_NOT_LOG'},
            'modbusConfig': {'channels': {'direct': {
                'protocol': 'modbus-tcp', 'registers': {'speed': {'address': 10}},
                'commands': {}, 'password': 'DO_NOT_LOG',
            }}},
        }
        callback(None, None, SimpleNamespace(payload=json.dumps({'devices': [device]}).encode()))
        refresh.assert_called_once_with([device])
        content = self.path.read_text()
        for expected in ('Configuración recibida', 'pump-1', '192.0.2.10',
                         'modbus-tcp', 'registers=1', 'Configuración cargada'):
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

    def test_connection_update_records_old_new_values_and_application(self):
        modules = {
            'infrastructure.logo.logo_client': SimpleNamespace(LogoModbusClient=Mock()),
            'infrastructure.modbus.modbus_tcp': SimpleNamespace(ModbusTcp=Mock()),
            'infrastructure.modbus.modbus_serial': SimpleNamespace(ModbusSerial=Mock()),
        }
        spec = importlib.util.spec_from_file_location('logged_device_service',
                                                    ROOT / 'application/services/device_service.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)
        device = SimpleNamespace(
            serial='pump-1', device_id='one', log=self.state.log, _lock=RLock(),
            _ALLOWED_CC_KEYS={'host', 'tcpPort', 'slaveId'},
            cc={'host': '192.0.2.10', 'tcpPort': 502, 'slaveId': 1},
            _normalize_connection_config=lambda: None,
            modbus_tcp=Mock(), modbus_serial=None, logo=None, update_fields=None,
        )
        module.DeviceService.update_connection_config(device, {'host': '192.0.2.20'})
        device.modbus_tcp.update_config.assert_called_once_with('192.0.2.20', 502, 1)
        content = self.path.read_text()
        self.assertIn('host: "192.0.2.10" → "192.0.2.20"', content)
        self.assertIn('Configuración de conexión aplicada a pump-1', content)

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
