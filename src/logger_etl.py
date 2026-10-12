"""Sistema de logs del ETL: un archivo nuevo por ejecución.

Requisito del taller (sección 5): cada ejecución genera un archivo
``logs/log_YYYYMMDD_HHMM.txt`` con fecha, hora, nivel (INFO/WARNING/ERROR) y
descripción del evento. Todos los módulos (extracción, transformación, carga,
pipeline) escriben en ese mismo archivo porque comparten el logger raíz
``etl_airbnb``.

Uso::

    from src.logger_etl import obtener_logger
    log = obtener_logger("extraccion")
    log.info("Conexión realizada")

El archivo se crea la primera vez que se pide un logger en el proceso. Dos
ejecuciones dentro del mismo minuto comparten archivo (se escribe en modo
append), consecuencia del formato de nombre que pide el enunciado.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from src.config import LOG_DIR

NOMBRE_RAIZ = "etl_airbnb"
FORMATO = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"

_archivo_actual: Path | None = None


def configurar_logging(
    directorio: Path | str | None = None,
    nivel: int = logging.INFO,
    consola: bool = True,
    nuevo_archivo: bool = False,
) -> Path:
    """Configura el logger raíz del ETL y devuelve la ruta del archivo de log.

    Es idempotente: si ya hay un archivo de log para esta ejecución se reutiliza,
    salvo que ``nuevo_archivo=True`` (útil en pruebas o en notebooks que quieran
    iniciar una ejecución limpia).
    """
    global _archivo_actual
    if _archivo_actual is not None and not nuevo_archivo:
        return _archivo_actual

    raiz = logging.getLogger(NOMBRE_RAIZ)
    for handler in list(raiz.handlers):
        handler.close()
        raiz.removeHandler(handler)

    carpeta = Path(directorio) if directorio else LOG_DIR
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / f"log_{datetime.now():%Y%m%d_%H%M}.txt"

    formato = logging.Formatter(FORMATO, FORMATO_FECHA)
    handler_archivo = logging.FileHandler(archivo, mode="a", encoding="utf-8")
    handler_archivo.setFormatter(formato)
    raiz.addHandler(handler_archivo)
    if consola:
        handler_consola = logging.StreamHandler(sys.stdout)
        handler_consola.setFormatter(formato)
        raiz.addHandler(handler_consola)

    raiz.setLevel(nivel)
    raiz.propagate = False  # evita duplicar mensajes si el notebook configura logging
    _archivo_actual = archivo
    return archivo


def obtener_logger(nombre: str) -> logging.Logger:
    """Devuelve un logger hijo (``etl_airbnb.<nombre>``) ya configurado."""
    configurar_logging()
    return logging.getLogger(f"{NOMBRE_RAIZ}.{nombre}")


def archivo_log_actual() -> Path | None:
    """Ruta del log de la ejecución en curso (None si aún no se configuró)."""
    return _archivo_actual
