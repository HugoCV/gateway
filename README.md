# Gateway

Gateway funciona como un servicio independiente de su ventana. El servicio es el
único proceso que abre conexiones MQTT, Modbus y LOGO. La interfaz consulta su
estado por un socket Unix local y privado; abrir varias ventanas o cerrarlas no
crea ni detiene conexiones a los dispositivos.

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
