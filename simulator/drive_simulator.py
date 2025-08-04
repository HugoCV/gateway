from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
from threading import Thread
import time
import random
from flask import Flask, jsonify

# —————— Configuración Modbus ——————
block = ModbusSequentialDataBlock(0, [
    1, 3703, 0, 0, 0,
    30, 40, 1110, 1
] + [0] * 91)
store   = ModbusSlaveContext(hr=block)
context = ModbusServerContext(slaves=store, single=True)

def simulate_drive():
    freq = speed = 0
    # valores fijos iniciales
    context[0].setValues(3, 1, [3703])
    context[0].setValues(3, 5, [30])
    context[0].setValues(3, 6, [40])
    context[0].setValues(3, 7, [1110])
    context[0].setValues(3, 8, [1])
    while True:
        stat      = block.getValues(0, 1)[0]
        freq_ref  = block.getValues(1, 1)[0]
        speed_ref = block.getValues(7, 1)[0]
        # lógica de simulación
        if stat == 1:
            variation = random.randint(-100, 100)
            target_freq = freq_ref + variation
            freq += random.choice([random.randint(50,150), -random.randint(50,150)]) \
                    if freq != target_freq else 0
            target_speed = speed_ref + random.randint(-50, 50)
            speed += random.choice([random.randint(10,30), -random.randint(10,30)]) \
                     if speed != target_speed else 0
        else:
            freq = speed = 0

        current = int((freq / 100) * random.uniform(0.5,1.2) * 10)
        # actualizar registros
        context[0].setValues(3, 2, [freq])
        context[0].setValues(3, 3, [current])
        context[0].setValues(3, 4, [speed])
        time.sleep(1)

# —————— Servidor HTTP (Flask) ——————
app = Flask(__name__)

@app.route('/status')
def status():
    # Leer algunos registros clave y devolverlos como JSON
    regs = block.getValues(0, 9)  # lee los primeros 9 registros
    keys = ['stat','freqRef','freq','current','speed','accTime','decTime','speedRef','dir']
    return jsonify({k: v for k, v in zip(keys, regs)})

def run_http():
    app.run(host='0.0.0.0', port=8000, debug=False)

# —————— Arranque de hilos ——————
Thread(target=simulate_drive, daemon=True).start()
Thread(target=run_http,        daemon=True).start()

print("✅ Variador simulado en Modbus TCP en puerto 5020 y HTTP en puerto 8000")
StartTcpServer(context, address=("0.0.0.0", 5020))
