# drivers/modbus_serial.py
from pymodbus.client import ModbusSerialClient

def read_register(port, baud, slave_id, reg_address, count=1):
    client = ModbusSerialClient(port=port, baudrate=baud, timeout=4)
    if not client.connect():
        raise ConnectionError(f"No se pudo conectar en {port}")
    rr = client.read_holding_registers(address=reg_address, count=count, slave=slave_id)
    client.close()
    if rr.isError():
        raise IOError(f"Error leyendo: {rr}")
    return rr.registers
