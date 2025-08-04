from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
from threading import Thread
import time
import random

# Crear bloque con espacio para 100 registros, prellenando los primeros valores
block = ModbusSequentialDataBlock(0, [
    1,      # 0: stat (RUN)
    3703,   # 1: freqRef (37.03 Hz * 100)
    0,      # 2: freq (Hz * 100)
    0,      # 3: current (A * 100)
    0,      # 4: speed (RPM)
    30,     # 5: accTime (3.0 s * 10)
    40,     # 6: decTime (4.0 s * 10)
    1110,   # 7: speedRef (RPM)
    1       # 8: dir (FORWARD)
] + [0] * 91)  # total 100 registros

store = ModbusSlaveContext(hr=block)
context = ModbusServerContext(slaves=store, single=True)

def simulate_drive():
    freq = 0
    speed = 0
    context[0].setValues(3, 1, [3703])
    context[0].setValues(3, 5, [30])
    context[0].setValues(3, 6, [40])
    context[0].setValues(3, 7, [1110])
    context[0].setValues(3, 8, [1])
    while True:
        # Leer valores de entrada
        stat      = block.getValues(0, 1)[0]
        freq_ref  = block.getValues(1, 1)[0]
        speed_ref = block.getValues(7, 1)[0]
        

        if stat == 1:
            variation = random.randint(-100, 100)
            target_freq = freq_ref + variation

            if freq < target_freq:
                freq += random.randint(50, 150)
            elif freq > target_freq:
                freq -= random.randint(50, 150)

            # velocidad simulada proporcional a frecuencia
            target_speed = speed_ref + random.randint(-50, 50)
            if speed < target_speed:
                speed += random.randint(10, 30)
            elif speed > target_speed:
                speed -= random.randint(10, 30)

        else:
            freq = 0
            speed = 0

        # corriente simulada en función de frecuencia
        load_factor = random.uniform(0.5, 1.2)
        current = int((freq / 100) * load_factor * 10)  # A * 100

        # Actualizar registros
        context[0].setValues(3, 2, [freq])
        context[0].setValues(3, 3, [current])
        context[0].setValues(3, 4, [speed])

        time.sleep(1)


# Iniciar hilo del simulador
Thread(target=simulate_drive, daemon=True).start()

print("✅ Variador simulado corriendo en Modbus TCP en puerto 5020")
StartTcpServer(context, address=("localhost", 5020))