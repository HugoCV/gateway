"""Persistent runtime activity and bounded, non-secret configuration summaries."""
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


CONNECTION_FIELDS = (
    'host', 'tcpIp', 'tcpPort', 'httpPort', 'serialPort', 'baudrate',
    'slaveId', 'logoIp', 'logoPort', 'mode', 'defaultReader',
)


def create_activity_logger(path=None, max_bytes=5 * 1024 * 1024, backups=3):
    path = Path(path) if path else Path(__file__).resolve().parents[1] / 'gateway.log'
    logger = logging.Logger('gateway.activity', level=logging.INFO)
    handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups,
                                  encoding='utf-8')
    handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S%z',
    ))
    logger.addHandler(handler)
    return logger


def log_value(value):
    # Escape newlines so received values cannot forge extra log entries.
    if not isinstance(value, (str, int, float, bool, type(None))):
        return '"[valor no escalar]"'
    return json.dumps(value, ensure_ascii=False)[:256]


def connection_summary(config):
    if not isinstance(config, dict):
        return '(sin configuración)'
    return ', '.join(f'{key}={log_value(config[key])}'
                     for key in CONNECTION_FIELDS if key in config) or '(vacía)'


def modbus_summary(config):
    if not isinstance(config, dict) or not isinstance(config.get('channels'), dict):
        return '(sin canales)'
    parts = []
    for name, channel in config['channels'].items():
        if not isinstance(channel, dict):
            continue
        counts = ', '.join(f'{key}={len(channel.get(key) or {})}'
                           for key in ('registers', 'commands', 'events')
                           if isinstance(channel.get(key) or {}, dict))
        parts.append(f'{log_value(name)}: protocolo={log_value(channel.get("protocol"))}, {counts}')
    return '; '.join(parts) or '(sin canales)'
