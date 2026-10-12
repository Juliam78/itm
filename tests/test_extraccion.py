import pytest

from src.extraccion import Extraccion, ErrorExtraccion


def _ext(cliente):
    return Extraccion(base_datos="airbnb_test", cliente=cliente)


def test_extrae_las_tres_colecciones_a_dataframes(cliente_mongo):
    with _ext(cliente_mongo) as ext:
        conteos = ext.validar_colecciones()
        listings, reviews, calendar = ext.extraer_listings(), ext.extraer_reviews(), ext.extraer_calendar()
    assert conteos == {"listings": 8, "reviews": 6, "calendar": 6}
    assert len(listings) == 8 and "_id" not in listings.columns
    assert len(reviews) == 6 and len(calendar) == 6


def test_campos_omitidos_quedan_como_nan_en_la_union_de_columnas(cliente_mongo):
    with _ext(cliente_mongo) as ext:
        listings = ext.extraer_listings()
    # el anuncio 7 no tiene 'price' en su documento
    assert listings["price"].isna().sum() == 1


def test_proyeccion_y_limite(cliente_mongo):
    with _ext(cliente_mongo) as ext:
        df = ext.extraer_coleccion("calendar", proyeccion={"date": 1}, limite=2)
    assert list(df.columns) == ["date"] and len(df) == 2


def test_calendario_mensual_agrega_en_mongodb(cliente_mongo):
    with _ext(cliente_mongo) as ext:
        mensual = ext.extraer_calendario_mensual().set_index(["listing_id", "mes"])
    assert mensual.loc[(1, "2026-06"), "dias_registrados"] == 3
    assert mensual.loc[(1, "2026-06"), "dias_disponibles"] == 2
    assert mensual.loc[(1, "2026-07"), "dias_disponibles"] == 0
    assert mensual.loc[(1, "2026-06"), "minimo_noches_promedio"] == pytest.approx(8 / 3)
    assert len(mensual) == 3


def test_coleccion_inexistente_lanza_error_claro(cliente_mongo):
    cliente_mongo["airbnb_test"].drop_collection("Reviews")
    with _ext(cliente_mongo) as ext, pytest.raises(ErrorExtraccion, match="ausentes o vacías"):
        ext.validar_colecciones()


def test_usar_sin_conectar_lanza_error(cliente_mongo):
    with pytest.raises(ErrorExtraccion):
        _ext(cliente_mongo).extraer_listings()


def test_el_log_registra_conexion_y_conteos(cliente_mongo, log_aislado):
    with _ext(cliente_mongo) as ext:
        ext.extraer_listings()
    texto = next(log_aislado.glob("log_*.txt")).read_text(encoding="utf-8")
    assert "Conexión exitosa con MongoDB" in texto
    assert "Extracción de 'Listings': 8 registros" in texto


def test_la_uri_con_credenciales_no_se_escribe_en_el_log():
    ext = Extraccion(uri="mongodb://usuario:secreto@host:27017/")
    assert "secreto" not in ext._uri_segura() and "usuario" not in ext._uri_segura()
