from pymodbus.client import ModbusTcpClient
import time

# Parámetros de conexión
DEVICE_IP = "localhost"   # o la IP de tu simulador, ej. "192.168.100.12"
DEVICE_PORT = 5020        # puerto donde corre tu simulador

# Crear cliente Modbus
client = ModbusTcpClient(DEVICE_IP, port=DEVICE_PORT)
print(f"🔌 Conectando a {DEVICE_IP}:{DEVICE_PORT} ...")

if not client.connect():
    raise Exception(f"❌ No se pudo conectar al simulador en {DEVICE_IP}:{DEVICE_PORT}")
print("✅ Conectado correctamente")

# --- Configurar frecuencia de referencia antes de arrancar ---
freq_ref_hz = 5.00
client.write_register(address=1, value=int(freq_ref_hz * 100))
print(f"⚙️  Frecuencia de referencia configurada a {freq_ref_hz:.2f} Hz")

# --- Encender variador (escribir 1 en registro 0) ---
client.write_register(address=0, value=1)
print("▶️ Comando RUN enviado")

# --- Leer señales mientras está RUN ---
for i in range(5):
    rr = client.read_holding_registers(address=0, count=4)
    if rr.isError():
        print(f"❌ Error al leer registros: {rr}")
    else:
        state, freq_ref, freq_actual, current = rr.registers
        print(f"[{i}] RUN -> Estado:{state}  "
              f"FreqRef:{freq_ref/100:.2f}Hz  "
              f"FreqActual:{freq_actual/100:.2f}Hz  "
              f"Corriente:{current/100:.2f}A")
    time.sleep(1)

# --- Apagar variador (escribir 0 en registro 0) ---
client.write_register(address=0, value=0)
print("⏹️ Comando STOP enviado")

# --- Leer señales mientras está STOP ---
for i in range(5):
    rr = client.read_holding_registers(address=0, count=4)
    if rr.isError():
        print(f"❌ Error al leer registros: {rr}")
    else:
        state, freq_ref, freq_actual, current = rr.registers
        print(f"[{i}] STOP -> Estado:{state}  "
              f"FreqRef:{freq_ref/100:.2f}Hz  "
              f"FreqActual:{freq_actual/100:.2f}Hz  "
              f"Corriente:{current/100:.2f}A")
    time.sleep(1)

# Cerrar conexión
client.close()
print("🔌 Conexión cerrada")
