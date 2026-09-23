"""Cold-start identity loading without a broker or the real configuration."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


class ConfigLoaderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.loader_path = self.root / 'infrastructure' / 'config' / 'loader.py'
        self.loader_path.parent.mkdir(parents=True)
        shutil.copyfile(Path(__file__).resolve().parents[1] /
                        'infrastructure/config/loader.py', self.loader_path)
        self.identity_path = self.root / 'state' / 'gateway.json'
        self.identity_path.parent.mkdir()
        self.identity = {'organizationId': 'test-org', 'gatewayId': 'test-gateway'}
        self.identity_path.write_text(json.dumps(self.identity))
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def load_module(self):
        spec = importlib.util.spec_from_file_location('cold_start_config', self.loader_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_cold_start_uses_path_from_dotenv_before_mqtt_import(self):
        (self.root / '.env').write_text(f'GATEWAY_CONFIG_PATH={self.identity_path}\n')
        module = self.load_module()
        self.assertEqual(module.GATEWAY_PATH, str(self.identity_path))
        self.assertEqual(module.get_gateway(), self.identity)

    def test_identity_from_dotenv_is_available_without_mqtt_import(self):
        (self.root / '.env').write_text(
            'GATEWAY_ORGANIZATION_ID=test-org\nGATEWAY_ID=test-gateway\n')
        self.assertEqual(self.load_module().get_gateway(), self.identity)

    def test_service_environment_takes_precedence_over_dotenv(self):
        os.environ['GATEWAY_CONFIG_PATH'] = str(self.identity_path)
        os.environ['GATEWAY_ID'] = 'service-gateway'
        (self.root / '.env').write_text(
            'GATEWAY_CONFIG_PATH=/unused/gateway.json\nGATEWAY_ID=dotenv-gateway\n')
        module = self.load_module()
        self.assertEqual(module.GATEWAY_PATH, str(self.identity_path))
        self.assertEqual(module.get_gateway(), {**self.identity, 'gatewayId': 'service-gateway'})

    def test_missing_identity_is_not_cached_when_file_becomes_available(self):
        os.environ['GATEWAY_CONFIG_PATH'] = str(self.identity_path)
        self.identity_path.unlink()
        module = self.load_module()
        self.assertEqual(module.get_gateway(), {})
        self.identity_path.write_text(json.dumps(self.identity))
        self.assertEqual(module.get_gateway(), self.identity)


if __name__ == '__main__':
    unittest.main()
