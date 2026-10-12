"""Importa los archivos fuente (.csv.gz) a MongoDB como colecciones Listings, Reviews y Calendar.

El enunciado del taller (sección "Aclaración sobre la carga en MongoDB") obliga
a cada grupo a crear la base de datos, importar los datasets como colecciones y
validar la importación ANTES de ejecutar el ETL. Este script hace esas tres cosas.
No forma parte del ETL: los CSV se usan únicamente aquí para poblar MongoDB.

Decisiones de importación (equivalentes a ``mongoimport --type csv --headerline``):
- Los valores vacíos NO se guardan en el documento (el campo se omite). Por eso
  algunas columnas 100 % vacías del CSV no existirán en la colección.
- Las fechas se guardan como texto ISO (YYYY-MM-DD), tal cual vienen; la
  conversión a fecha se hace en la transformación.
- Los números se guardan como int/double según el contenido del CSV.

Uso::

    python scripts/cargar_mongodb.py                       # usa datos/fuente/*.csv.gz
    python scripts/cargar_mongodb.py --datos-dir C:/ruta   # otra carpeta
    python scripts/cargar_mongodb.py --reemplazar          # borra y recarga las colecciones
    python scripts/cargar_mongodb.py --solo listings reviews
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo import MongoClient  # noqa: E402
from pymongo.errors import PyMongoError  # noqa: E402

from src.config import (  # noqa: E402
    ARCHIVOS_FUENTE, COLECCIONES, DATOS_FUENTE_DIR, MONGO_DATABASE, MONGO_TIMEOUT_MS, MONGO_URI,
    resolver_archivo_fuente,
)
from src.logger_etl import obtener_logger  # noqa: E402

log = obtener_logger("cargar_mongodb")
TAMANO_LOTE = 50_000


def _registros(df: pd.DataFrame):
    """Convierte un DataFrame a diccionarios omitiendo los valores nulos."""
    for fila in df.to_dict("records"):
        yield {k: v for k, v in fila.items() if not pd.isna(v)}


def importar(clave: str, ruta: Path, coleccion, reemplazar: bool) -> int:
    """Importa un .csv.gz por lotes y devuelve la cantidad de documentos insertados."""
    nombre = coleccion.name
    existentes = coleccion.estimated_document_count()
    if existentes and not reemplazar:
        log.warning("La colección '%s' ya tiene %s documentos; se omite (use --reemplazar para recargarla)", nombre, f"{existentes:,}")
        return 0
    if existentes:
        log.warning("Se elimina el contenido previo de '%s' (%s documentos)", nombre, f"{existentes:,}")
        coleccion.drop()

    inicio = time.perf_counter()
    total = 0
    # listings tiene texto multilínea y 90 columnas: se lee en bloques con tipos inferidos por bloque.
    for lote in pd.read_csv(ruta, chunksize=TAMANO_LOTE, low_memory=False):
        documentos = list(_registros(lote))
        if documentos:
            coleccion.insert_many(documentos, ordered=False)
        total += len(documentos)
        log.info("%s: %s documentos insertados...", nombre, f"{total:,}")
    log.info("Importación de '%s' terminada: %s documentos (%.1f s)", nombre, f"{total:,}", time.perf_counter() - inicio)
    return total


def contar_filas_csv(ruta: Path) -> int:
    """Cuenta registros reales del CSV (no líneas: hay textos con saltos de línea)."""
    return sum(len(b) for b in pd.read_csv(ruta, usecols=[0], chunksize=200_000))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Importa los datasets de Airbnb a MongoDB local")
    parser.add_argument("--datos-dir", type=Path, default=DATOS_FUENTE_DIR)
    parser.add_argument("--reemplazar", action="store_true")
    parser.add_argument("--solo", nargs="+", choices=list(ARCHIVOS_FUENTE), help="Importar solo estas colecciones")
    args = parser.parse_args(argv)

    claves = args.solo or list(ARCHIVOS_FUENTE)
    rutas = {c: resolver_archivo_fuente(args.datos_dir, c) for c in claves}
    faltantes = [ARCHIVOS_FUENTE[c][0] for c, r in rutas.items() if r is None]
    if faltantes:
        log.error("No se encuentran en %s los archivos fuente: %s", args.datos_dir, faltantes)
        print("Copie listings.csv.gz, reviews.csv.gz y calendar.csv.gz en", args.datos_dir)
        return 1

    try:
        cliente = MongoClient(MONGO_URI, serverSelectionTimeoutMS=MONGO_TIMEOUT_MS)
        cliente.admin.command("ping")
    except PyMongoError as error:
        log.error("No hay conexión con MongoDB: %s", error)
        return 1
    log.info("Conectado a MongoDB; base de datos '%s'", MONGO_DATABASE)
    db = cliente[MONGO_DATABASE]

    for clave, ruta in rutas.items():
        importar(clave, ruta, db[COLECCIONES[clave]], args.reemplazar)

    # Validación posterior a la importación (exigida por el enunciado).
    ok = True
    for clave, ruta in rutas.items():
        esperado = contar_filas_csv(ruta)
        cargado = db[COLECCIONES[clave]].count_documents({})
        if esperado == cargado:
            log.info("VALIDACIÓN OK '%s': %s documentos = %s filas del CSV", COLECCIONES[clave], f"{cargado:,}", f"{esperado:,}")
        else:
            ok = False
            log.error("VALIDACIÓN FALLIDA '%s': %s documentos vs %s filas del CSV", COLECCIONES[clave], f"{cargado:,}", f"{esperado:,}")

    # Índices que aceleran filtros por anuncio (la agregación mensual no los necesita).
    for clave, campo in (("listings", "id"), ("reviews", "listing_id"), ("calendar", "listing_id")):
        if clave in rutas:
            db[COLECCIONES[clave]].create_index(campo)
            log.info("Índice creado: %s.%s", COLECCIONES[clave], campo)
    cliente.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
