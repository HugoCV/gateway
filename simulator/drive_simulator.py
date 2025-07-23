from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
from threading import Thread
import time

# Registros simulados:
# 0: estado (0=STOP, 1=RUN)
# 1: frecuencia de referencia (Hz * 100)
# 2: frecuencia actual (Hz * 100)
# 3: corriente (A * 100)
# 4: código de alarma (0=sin alarma)
block = ModbusSequentialDataBlock(0, [0, 500, 0, 0, 0] + [0]*95)
store = ModbusSlaveContext(hr=block)
context = ModbusServerContext(slaves=store, single=True)

def simulate_drive():
    while True:
        state = block.getValues(0, 1)[0]      
        freq_ref = block.getValues(1, 1)[0]   
        freq_actual = block.getValues(2, 1)[0] 
        if state == 1:
            if freq_actual < freq_ref:
                freq_actual += 10
            elif freq_actual > freq_ref:
                freq_actual -= 10
        else:
            freq_actual = 0

        current = int(freq_actual / 20)
        block.setValues(2, [freq_actual])  
        block.setValues(3, [current])     

        time.sleep(1)

t = Thread(target=simulate_drive, daemon=True)
t.start()

print("✅ Variador simulado corriendo en Modbus TCP en puerto 5020")
StartTcpServer(context, address=("localhost", 5020))
