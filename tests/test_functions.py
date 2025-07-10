import unittest
from unittest import mock
import subprocess
import builtins
import os

import importlib.util
from pathlib import Path
import sys
import types

sys.modules['config'] = types.SimpleNamespace(use_availability=False, ext_sensors=False, version="0")

SRC_DIR = Path(__file__).parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

import update
import ext_sensor_lib.ds18b20 as ds18b20

# Insert mocks for optional third party libraries so tests run without them
paho_module = types.ModuleType("paho")
paho_mqtt_module = types.ModuleType("paho.mqtt")
paho_client_module = types.ModuleType("paho.mqtt.client")
paho_mqtt_module.client = paho_client_module
paho_module.mqtt = paho_mqtt_module
sys.modules['paho'] = paho_module
sys.modules['paho.mqtt'] = paho_mqtt_module
sys.modules['paho.mqtt.client'] = paho_client_module
sys.modules['psutil'] = types.ModuleType("psutil")
sys.modules['requests'] = types.ModuleType("requests")

spec = importlib.util.spec_from_file_location("monitor", str(SRC_DIR / "rpi-cpu2mqtt.py"))
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)

class TestFunctions(unittest.TestCase):
    def test_check_sys_clock_speed(self):
        mock_data = '1500000\n'
        with mock.patch.object(builtins, 'open', mock.mock_open(read_data=mock_data)):
            self.assertEqual(monitor.check_sys_clock_speed(), 1500)

    def test_get_assignments(self):
        with open('tmp_config.py', 'w') as f:
            f.write('var1 = 1\nvar2 = "test"\n')
        try:
            result = update.get_assignments('tmp_config.py')
            self.assertEqual(result['var1'], 1)
            self.assertEqual(result['var2'], 'test')
        finally:
            os.remove('tmp_config.py')

    def test_check_git_version_remote(self):
        mock_completed = mock.Mock(stdout='v1.0\nv0.9\n', returncode=0)
        with mock.patch('subprocess.run', return_value=mock_completed) as m:
            version = update.check_git_version_remote('/tmp')
            self.assertEqual(version, 'v1.0')
            expected_calls = [
                mock.call([
                    'git', '-C', '/tmp', 'fetch', '--tags'
                ], check=True, stdout=mock.ANY, stderr=mock.ANY, text=True),
                mock.call([
                    'git', '-C', '/tmp', 'tag', '--sort=-v:refname'
                ], check=True, stdout=mock.ANY, stderr=mock.ANY, text=True)
            ]
            m.assert_has_calls(expected_calls)

    def test_install_requirements_error(self):
        with mock.patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, 'cmd')):
            with self.assertRaises(SystemExit):
                update.install_requirements('/tmp')

    def test_sanitize_numeric(self):
        self.assertEqual(monitor.sanitize_numeric(10), 10)
        self.assertEqual(monitor.sanitize_numeric(None), 0)
        self.assertEqual(monitor.sanitize_numeric(float('nan')), 0)

    def test_sensor_ds18b20_success(self):
        sensor_output = (
            '76 01 4b 46 7f ff 0c 10 e6 : crc=e6 YES\n'
            '76 01 4b 46 7f ff 0c 10 e6 t=23125\n'
        )
        with mock.patch.object(builtins, 'open', mock.mock_open(read_data=sensor_output)):
            self.assertEqual(ds18b20.sensor_DS18B20('0000'), 23.1)

    def test_sensor_ds18b20_missing_file(self):
        with mock.patch.object(builtins, 'open', side_effect=IOError):
            self.assertEqual(ds18b20.sensor_DS18B20('0000'), -300.0)

if __name__ == '__main__':
    unittest.main()

