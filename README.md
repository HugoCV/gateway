# Gateway

Gateway funciona como un servicio independiente de su ventana. El servicio es el
único proceso que abre conexiones MQTT, Modbus y LOGO. La interfaz consulta su
estado por un socket Unix local y privado; abrir varias ventanas o cerrarlas no
crea ni detiene conexiones a los dispositivos.

## Arranque directo

Desde la carpeta del proyecto, con el entorno `venv` y las dependencias instaladas:

```bash
./start.sh
```

Este comando inicia el motor en segundo plano si hace falta y abre la ventana.
No requiere el instalador ni systemd. Si el motor ya responde, reutiliza ese
proceso. Cerrar la ventana deja el motor funcionando; puede abrirla de nuevo
ejecutando el mismo comando. Los errores del motor se guardan en `gateway.log`.

Ambos procesos usan `GATEWAY_CONFIG_PATH` si está definida. En caso contrario,
usan `/var/lib/alrotek-gateway/gateway.json` si existe, para conservar la identidad
de una instalación anterior; si no existe, usan `data/gateway.json` del proyecto.

## Historial de actividad

El motor escribe `gateway.log` en la carpeta del proyecto, tanto con `./start.sh`
como al ejecutarse en modo `headless`. Cada entrada incluye fecha, hora y zona
horaria. Registra las configuraciones recibidas por MQTT, un resumen de conexiones
y canales Modbus por dispositivo, los cambios de valores (anterior → nuevo),
los comandos y sus resultados, y los mensajes de conexión y error del motor.
Una configuración aplicada no significa que el equipo haya conectado: los
mensajes de conexión se registran por separado.

El archivo conserva el historial entre reinicios y rota al alcanzar 5 MiB,
manteniendo tres copias: `gateway.log.1`, `.2` y `.3`. No guarda los mensajes MQTT
completos ni convierte el historial en una copia de configuración para arrancar
sin conexión. Los resúmenes de conexión incluyen únicamente campos técnicos.

Para ver la actividad en vivo:

```bash
tail -f gateway.log
```

`gateway-startup.log` contiene la salida adicional de consola y los errores de
arranque al usar `./start.sh`; se reemplaza al iniciar un nuevo motor. El historial
con fechas permanece en `gateway.log` y sus copias.

## En el equipo instalado

El instalador 1.2.0 habilita `alrotek-gateway.service` al encender el equipo y abre
la interfaz al iniciar sesión en el escritorio. La ventana puede abrirse de nuevo
desde **Alrotek Gateway** en el menú de aplicaciones o con `~/gateway/start.sh`.

La interfaz muestra la conectividad, los dispositivos y los últimos 250 mensajes
emitidos mediante el registro del controlador. Si el servicio tarda en arrancar
o se reinicia, muestra que está esperando y vuelve a conectarse automáticamente.
Al cerrar la sesión, el servicio continúa funcionando. Sin escritorio no puede
mostrarse una ventana.

“Guardar y reiniciar servicio” guarda la identidad externa y reinicia el servicio;
la ventana permanece abierta. Si `GATEWAY_ORGANIZATION_ID` o `GATEWAY_ID` están
fijados en `.env`, deben modificarse allí: estos valores tienen prioridad sobre
el archivo de identidad. Los registros completos del servicio están en:

```bash
journalctl -u alrotek-gateway -f
```

## Desarrollo

Se requiere Python 3.10+ y las dependencias de `requirements.txt`. Ejecute los dos
procesos por separado usando la misma cuenta y `GATEWAY_CONFIG_PATH`:

```bash
GATEWAY_CONFIG_PATH=/ruta/privada/gateway.json python3 main.py --mode headless
GATEWAY_CONFIG_PATH=/ruta/privada/gateway.json python3 main.py --mode gui
```

El socket se crea en `runtime/control.sock` junto al archivo de identidad, con
permisos 0600 dentro de un directorio 0700. No expone un puerto de red. El bloqueo
del runtime impide iniciar un segundo servicio; las ventanas no toman ese bloqueo.

En instalaciones anteriores, cierre la antigua ventana operativa antes de
actualizar. Publique primero el Gateway actualizado y luego use el instalador
1.2.0 apuntando a esa revisión. No es necesario modificar el backend ni el cliente web.

## Verificación

```bash
python3 -m compileall -q application infrastructure domain ui main.py
python3 -m unittest discover -s tests -v
```

Las pruebas no usan dispositivos ni MQTT. Las pruebas de comunicación local
requieren que el entorno permita crear sockets Unix.
