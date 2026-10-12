"""Orquestador del ETL: Extracción (MongoDB) → Transformación → Carga (SQLite + XLSX).

Ejecución::

    python -m src.pipeline                       # ETL completo
    python -m src.pipeline --sin-xlsx            # solo SQLite
    python -m src.pipeline --calendar omitir     # sin la tabla de disponibilidad

Estructura tomada del ``src/pipeline.py`` del repositorio de ejemplo: configurar
logs, ejecutar las etapas en orden, registrar con ``log.exception`` cualquier
error y relanzarlo. La diferencia es que aquí el log es un archivo por ejecución.
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from src.carga import Carga
from src.extraccion import Extraccion
from src.logger_etl import archivo_log_actual, configurar_logging, obtener_logger
from src.transformacion import Transformacion


def ejecutar_pipeline(
    calendar: str = "mensual",
    exportar_xlsx: bool = True,
    eliminar_sin_precio: bool = False,
    cliente_mongo: Any = None,
    base_datos: str | None = None,
    ruta_sqlite=None,
    dir_xlsx=None,
) -> dict:
    """Ejecuta el ETL completo y devuelve ``{"tablas", "carga", "log"}``.

    ``cliente_mongo`` y ``base_datos`` permiten inyectar un cliente alterno (p. ej. ``mongomock``) en pruebas.
    """
    configurar_logging()
    log = obtener_logger("pipeline")
    inicio = time.perf_counter()
    log.info("##### INICIO DEL ETL AIRBNB BOGOTÁ #####")
    log.info("Parámetros: calendar=%s, exportar_xlsx=%s, eliminar_sin_precio=%s", calendar, exportar_xlsx, eliminar_sin_precio)
    try:
        kw_mongo = {"base_datos": base_datos} if base_datos else {}
        with Extraccion(cliente=cliente_mongo, **kw_mongo) as extraccion:
            fuentes = extraccion.extraer_todo(calendar=calendar)

        tablas = Transformacion(eliminar_sin_precio=eliminar_sin_precio).ejecutar(fuentes)

        kwargs = {k: v for k, v in {"ruta_sqlite": ruta_sqlite, "dir_xlsx": dir_xlsx}.items() if v is not None}
        resultado_carga = Carga(**kwargs).cargar_todo(tablas, exportar_xlsx=exportar_xlsx)
    except Exception:
        log.exception("El ETL terminó con un error")
        raise
    log.info("##### ETL FINALIZADO CORRECTAMENTE en %.1f s #####", time.perf_counter() - inicio)
    return {"tablas": tablas, "carga": resultado_carga, "log": archivo_log_actual()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ETL Airbnb Bogotá: MongoDB → SQLite + XLSX")
    parser.add_argument("--calendar", choices=["mensual", "completo", "omitir"], default="mensual",
                        help="Cómo extraer Calendar (7 M de filas): agregado mensual en MongoDB (defecto), completo u omitir")
    parser.add_argument("--sin-xlsx", action="store_true", help="No generar los archivos XLSX")
    parser.add_argument("--eliminar-sin-precio", action="store_true", help="Descartar anuncios sin precio")
    args = parser.parse_args(argv)
    ejecutar_pipeline(
        calendar=args.calendar,
        exportar_xlsx=not args.sin_xlsx,
        eliminar_sin_precio=args.eliminar_sin_precio,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
