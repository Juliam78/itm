"""Configuración central del ETL de Airbnb Bogotá.

Los valores salen de variables de entorno (archivo .env) con valores por
defecto pensados para un MongoDB local sin autenticación. Nunca se escriben
credenciales en el código: si el Mongo del grupo exige usuario y clave, van
dentro de MONGO_URI en el archivo .env (que está en .gitignore).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def _ruta(valor: str) -> Path:
    """Convierte una ruta del .env en absoluta respecto a la raíz del proyecto."""
    ruta = Path(valor)
    return ruta if ruta.is_absolute() else BASE_DIR / ruta


# --- MongoDB (fuente obligatoria del taller) ---------------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "airbnb_bogota")
MONGO_TIMEOUT_MS = int(os.getenv("MONGO_TIMEOUT_MS", "5000"))

# El enunciado nombra las colecciones con mayúscula inicial.
COLECCIONES = {
    "listings": os.getenv("COL_LISTINGS", "Listings"),
    "reviews": os.getenv("COL_REVIEWS", "Reviews"),
    "calendar": os.getenv("COL_CALENDAR", "Calendar"),
}

# --- Rutas --------------------------------------------------------------------
DATOS_FUENTE_DIR = _ruta(os.getenv("DATOS_FUENTE_DIR", "datos/fuente"))
SQLITE_PATH = _ruta(os.getenv("SQLITE_PATH", "sqlite/airbnb_bogota.db"))
SALIDA_DIR = _ruta(os.getenv("SALIDA_DIR", "datos/salida"))
LOG_DIR = BASE_DIR / "logs"

# Archivos fuente que entrega el profesor (solo se usan para poblar MongoDB).
# El enunciado los llama listings.csv.gz, pero al descargarlos de Teams/Moodle a veces
# quedan como listings_csv.gz; se aceptan ambos nombres.
ARCHIVOS_FUENTE = {
    "listings": ("listings.csv.gz", "listings_csv.gz"),
    "reviews": ("reviews.csv.gz", "reviews_csv.gz"),
    "calendar": ("calendar.csv.gz", "calendar_csv.gz"),
}


def resolver_archivo_fuente(directorio: Path, clave: str) -> Path | None:
    """Devuelve la ruta existente del archivo fuente de ``clave`` o None si no está."""
    for nombre in ARCHIVOS_FUENTE[clave]:
        if (Path(directorio) / nombre).exists():
            return Path(directorio) / nombre
    return None

# --- Reglas de transformación --------------------------------------------------
# Rangos de precio por noche en COP. Los cortes se acercan a los percentiles
# 25/50/75/95 observados al inspeccionar listings (≈110k, 161k, 230k, 498k).
# Son una decisión de negocio ajustable: confirmar con el EDA antes de entregar.
PRECIO_CORTES = [0, 110_000, 160_000, 230_000, 500_000, float("inf")]
PRECIO_ETIQUETAS = ["Económico", "Bajo", "Medio", "Alto", "Premium"]

# Factor del criterio IQR para marcar (no eliminar) valores atípicos extremos de precio.
FACTOR_IQR_ATIPICOS = 3.0

# minimum_nights se concentra en 1-3 noches (Q1=1, Q3=3), así que el criterio IQR marcaría
# ~20 % de los anuncios (> 9 noches) y dejaría de ser un "atípico". Se usa una regla de
# negocio: estadía mínima superior a un mes (84 anuncios en junio 2026, máximo = 32).
UMBRAL_MINIMO_NOCHES = 30
