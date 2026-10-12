"""Datos sintéticos mínimos con los mismos defectos que se observaron en los archivos reales.

Los formatos (precio '$284,294.01', amenities en JSON con escapes unicode, fechas ISO,
't'/'f', '<br/>' en reseñas, maximum_nights = 2147483647) están copiados de la
inspección de listings/calendar/reviews de junio 2026.
"""
import json

import mongomock
import pandas as pd
import pytest

from src.logger_etl import configurar_logging


@pytest.fixture(autouse=True)
def log_aislado(tmp_path):
    """Cada prueba escribe su log en una carpeta temporal (no ensucia logs/)."""
    configurar_logging(directorio=tmp_path / "logs", nuevo_archivo=True, consola=False)
    return tmp_path / "logs"


def _listing(i, **extra):
    base = {
        "id": i, "name": f"Anuncio {i}", "description": "Texto<br/>con   saltos", "host_id": 100 + (i % 2),
        "host_name": f"Host {i % 2}", "host_is_superhost": "t" if i % 2 else "f", "host_listings_count": 2,
        "last_scraped": "2026-06-22", "room_type": "Entire home/apt", "property_type": "Entire rental unit",
        "bathrooms_text": "1 shared bath" if i == 1 else "2 baths", "bedrooms": 1.0,
        "amenities": json.dumps(["Wifi", "Kitchen", "Children\u2019s books and toys", "Wifi"]),
        "price": "$100,000.00", "minimum_nights": 1.0, "availability_365": 300,
        "first_review": "2020-01-15", "last_review": "2025-09-14", "review_scores_rating": 4.8,
    }
    base.update(extra)
    return base


@pytest.fixture
def docs_listings():
    return [
        _listing(1, price="$284,294.01"),
        _listing(2, price="$55,000.00", minimum_nights=2.0),
        _listing(3, price="$1,500,000.00", minimum_nights=1.0),
        _listing(4, price="$180,000.00", minimum_nights=45.0),
        _listing(5, price="$120,000.00"),
        _listing(6, price="$95,000.00", amenities="[]"),
        {k: v for k, v in _listing(7).items() if k != "price"},          # sin precio (campo ausente)
        _listing(8, price="$448,176,567.00"),                           # precio extremo
    ]


@pytest.fixture
def docs_reviews():
    return [
        {"listing_id": 1, "id": 10, "date": "2021-03-05", "reviewer_id": 1, "reviewer_name": " Ana ", "comments": "Muy bueno.<br/><br/>Volvería\r\n"},
        {"listing_id": 1, "id": 11, "date": "2024-12-31", "reviewer_id": 2, "reviewer_name": "Luis"},          # sin comments
        {"listing_id": 2, "id": 12, "date": "2025-06-01", "reviewer_id": 3, "reviewer_name": "Eva", "comments": "ok"},
        {"listing_id": 99, "id": 13, "date": "2025-06-01", "reviewer_id": 4, "reviewer_name": "Zoe", "comments": "huérfana"},
        {"listing_id": 2, "id": 12, "date": "2025-06-01", "reviewer_id": 3, "reviewer_name": "Eva", "comments": "ok"},  # duplicada
        {"listing_id": 2, "id": 14, "date": "no-es-fecha", "reviewer_id": 5, "reviewer_name": "Max", "comments": "fecha mala"},
    ]


@pytest.fixture
def docs_calendar():
    """Listing 1: 3 días de junio (2 libres) + 2 de julio (0 libres); listing 2: 1 día."""
    filas = [
        (1, "2026-06-21", "t", 2, 1125), (1, "2026-06-22", "t", 2, 1125), (1, "2026-06-23", "f", 4, 2147483647),
        (1, "2026-07-01", "f", 2, 1125), (1, "2026-07-02", "f", 2, 1125),
        (2, "2026-06-21", "t", 1, 365),
    ]
    return [{"listing_id": a, "date": b, "available": c, "minimum_nights": d, "maximum_nights": e} for a, b, c, d, e in filas]


@pytest.fixture
def cliente_mongo(docs_listings, docs_reviews, docs_calendar):
    """Cliente mongomock con las tres colecciones del taller ya cargadas (NO es un MongoDB real)."""
    cliente = mongomock.MongoClient()
    db = cliente["airbnb_test"]
    db["Listings"].insert_many([dict(d) for d in docs_listings])
    db["Reviews"].insert_many([dict(d) for d in docs_reviews])
    db["Calendar"].insert_many([dict(d) for d in docs_calendar])
    return cliente
