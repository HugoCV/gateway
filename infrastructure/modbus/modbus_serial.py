# drivers/modbus_serial.py
import platform
from pymodbus.client import ModbusSerialClient
from serial import Serial
from serial.rs485 import RS485Settings

def _create_rs485_serial(port, baudrate, timeout):
    """
    Create a serial port with RS-485 settings enabled.

    Args:
        port (str): Serial port name, e.g. "/dev/ttyUSB0" or "COM3"
        baudrate (int): Baud rate
        timeout (int): Read timeout in seconds

    Returns:
        Serial: Configured serial instance with RS-485 mode
    """
    ser = Serial(port=port, baudrate=baudrate, timeout=timeout)
    ser.rs485_mode = RS485Settings(
        rts_level_for_tx=True,
        rts_level_for_rx=False,
        delay_before_tx=None,
        delay_before_rx=None
    )
    return ser

def read_register(port, baudrate, slave_id, reg_address, count=1, timeout=4):
    """
    Read Modbus RTU holding registers over RS-485.

    Args:
        port (str): Serial port name
        baudrate (int): Baud rate
        slave_id (int): Modbus slave address
        reg_address (int): Starting register address
        count (int): Number of registers to read
        timeout (int): Timeout in seconds

    Returns:
        list[int]: Register values
    """
    try:
        ser = _create_rs485_serial(port, baudrate, timeout)
        client = ModbusSerialClient(
            method="rtu",
            port=ser,
            timeout=timeout
        )
        if not client.connect():
            raise ConnectionError(f"Unable to connect to {port}")

        rr = client.read_holding_registers(
            address=reg_address,
            count=count,
            slave=slave_id
        )
        client.close()

        if rr.isError():
            raise IOError(f"Modbus error: {rr}")

        return rr.registers

    except Exception as e:
        raise RuntimeError(f"Modbus RTU read failure on {port}: {e}")
