import unittest
from unittest.mock import Mock

from infrastructure.modbus.configured_channel import ConfiguredModbusChannel


def make_channel(items):
    return ConfiguredModbusChannel(
        channel={
            "id": "main",
            "name": "Principal",
            "protocol": "modbus-tcp",
            "items": items,
        },
        connection={"host": "127.0.0.1", "port": 5020, "slaveId": 7},
        on_signal=Mock(),
        on_status=Mock(),
        log=Mock(),
    )


class ConfiguredChannelTests(unittest.TestCase):
    def test_decodes_int16_only_when_signed_is_enabled(self):
        signed = {"kind": "measurement", "read": {"signed": True, "scale": 0.1, "absolute": True}}
        unsigned = {"kind": "measurement", "read": {"signed": False, "scale": 0.1}}

        self.assertEqual(
            ConfiguredModbusChannel._decode(signed, 0xFFF6),
            {"value": 1, "rawValue": 0xFFF6, "kind": "measurement"},
        )
        self.assertEqual(
            ConfiguredModbusChannel._decode(unsigned, 0xFFF6)["value"],
            6552.6,
        )

    def test_executes_only_an_action_declared_by_stable_item_and_action_ids(self):
        runtime = make_channel([{
            "id": "power_control",
            "capability": "write",
            "write": {"actions": [{
                "id": "turn_on", "address": 897, "value": 3, "writeMode": "replace",
            }]},
            "presentation": {"type": "button"},
        }])
        runtime.client = Mock()
        runtime.client.is_socket_open.return_value = True
        runtime.write_register = Mock(return_value=True)

        self.assertEqual(runtime.execute_action("power_control", "turn_on"), (True, None))
        runtime.write_register.assert_called_once_with(897, 3)
        self.assertEqual(
            runtime.execute_action("power_control", "not_configured"),
            (False, "configured_action_not_found"),
        )

    def test_masked_actions_preserve_unrelated_register_bits(self):
        runtime = make_channel([{
            "id": "mode",
            "capability": "read-write",
            "write": {"actions": [{
                "id": "remote", "address": 100, "value": 0b0100,
                "writeMode": "masked", "mask": 0b0110,
            }]},
            "presentation": {"type": "switch"},
        }])
        runtime.client = Mock()
        runtime.client.is_socket_open.return_value = True
        runtime.read_register = Mock(return_value=0b1001)
        runtime.write_register = Mock(return_value=True)

        self.assertEqual(runtime.execute_action("mode", "remote"), (True, None))
        runtime.write_register.assert_called_once_with(100, 0b1101)


if __name__ == "__main__":
    unittest.main()
