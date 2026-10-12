"""Prueba con una MUESTRA de los archivos reales cargada en mongomock.

Se omite sola si no están los archivos. Para ejecutarla::

    set AIRBNB_DATA_DIR=C:/ruta/a/los/csv.gz            (Windows)
    export AIRBNB_DATA_DIR=/ruta/a/los/csv.gz           (Linux/macOS)
    pytest tests/test_datos_reales.py -v -s

IMPORTANTE: usa ``mongomock`` (simulador en memoria), NO un MongoDB real. Sirve para
comprobar que el código funciona con la estructura real de los datos (90 columnas,
precios con '$', amenities en JSON, etc.), pero no reemplaza la validación contra el
MongoDB local del grupo.
"""
import os
import sqlite3
from pathlib import Path

import mongomock
import pandas as pd
import pytest

from src.config import ARCHIVOS_FUENTE, resolver_archivo_fuente
from src.pipeline import ejecutar_pipeline

DATOS = os.getenv("AIRBNB_DATA_DIR")
pytestmark = pytest.mark.skipif(
    not DATOS or not all(resolver_archivo_fuente(DATOS, c) for c in ARCHIVOS_FUENTE),
    reason="Defina AIRBNB_DATA_DIR con los tres .csv.gz para ejecutar esta prueba",
)
N_ANUNCIOS = 400


def _docs(df):
    # misma regla que scripts/cargar_mongodb.py: los valores vacíos se omiten del documento
    return [{k: v for k, v in fila.items() if not pd.isna(v)} for fila in df.to_dict("records")]


@pytest.fixture(scope="module")
def cliente_real():
    listings = pd.read_csv(resolver_archivo_fuente(DATOS, "listings"), low_memory=False).head(N_ANUNCIOS)
    ids = set(listings["id"])
    reviews = pd.read_csv(resolver_archivo_fuente(DATOS, "reviews"))
    reviews = reviews[reviews["listing_id"].isin(ids)]
    calendar = pd.concat(
        [c[c["listing_id"].isin(ids)] for c in pd.read_csv(resolver_archivo_fuente(DATOS, "calendar"), chunksize=500_000)]
    )
    cliente = mongomock.MongoClient()
    db = cliente["airbnb_real_muestra"]
    db["Listings"].insert_many(_docs(listings))
    db["Reviews"].insert_many(_docs(reviews))
    db["Calendar"].insert_many(_docs(calendar))
    cliente.esperado = {"listings": len(listings), "reviews": len(reviews), "calendar": len(calendar)}
    return cliente


def test_pipeline_con_muestra_real(cliente_real, tmp_path):
    r = ejecutar_pipeline(cliente_mongo=cliente_real, base_datos="airbnb_real_muestra",
                          ruta_sqlite=tmp_path / "real.db", dir_xlsx=tmp_path / "xlsx")
    t, esperado = r["tablas"], cliente_real.esperado
    assert r["carga"]["verificacion"]["ok"].all()
    assert len(t["listings"]) == esperado["listings"]
    assert len(t["reviews"]) == esperado["reviews"]            # no hay huérfanas ni duplicadas en el dataset
    assert t["listings"]["price"].dropna().gt(0).all()
    assert t["calendario_mensual"]["dias_registrados"].sum() == esperado["calendar"]
    with sqlite3.connect(tmp_path / "real.db") as con:
        assert con.execute("SELECT COUNT(*) FROM listing_amenities").fetchone()[0] > 0
    print("\nTablas:", {k: v.shape for k, v in t.items()})
    print("Log:", r["log"])
