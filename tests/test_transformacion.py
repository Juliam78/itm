import numpy as np
import pandas as pd
import pytest

from src.extraccion import Extraccion
from src.transformacion import (
    ErrorTransformacion, Transformacion, a_booleano, limpiar_precio, limpiar_texto,
    marcar_atipicos_iqr, parsear_amenities,
)


# ---------------------------------------------------------------- funciones puras
def test_limpiar_precio_quita_simbolos_y_convierte():
    s = limpiar_precio(pd.Series(["$284,294.01", "$215,000.00", None, "abc"]))
    assert s.iloc[0] == pytest.approx(284294.01) and s.iloc[1] == 215000.0
    assert s.iloc[2:].isna().all()


def test_a_booleano_maneja_nulos():
    r = a_booleano(pd.Series(["t", "f", None, "T"]))
    assert r.tolist()[:2] == [1, 0] and pd.isna(r.iloc[2]) and r.iloc[3] == 1


def test_limpiar_texto_quita_br_control_y_espacios():
    s = limpiar_texto(pd.Series(["Hola<br/><br/>mundo \r\n  fin\x07", None]))
    assert s.iloc[0] == "Hola mundo fin" and pd.isna(s.iloc[1])


def test_parsear_amenities_json_y_respaldo():
    lista, ok = parsear_amenities('["Wifi", "Children\\u2019s books", "Wifi"]')
    assert ok and lista == ["Wifi", "Children’s books"]
    lista, ok = parsear_amenities("[Wifi, Kitchen]")
    assert not ok and lista == ["Wifi", "Kitchen"]
    assert parsear_amenities(None) == ([], True) and parsear_amenities(float("nan")) == ([], True)


def test_marcar_atipicos_no_elimina():
    s = pd.Series([1, 1, 2, 2, 3, 1000.0, np.nan])
    bandera, limite = marcar_atipicos_iqr(s)
    assert bandera.iloc[5] == 1 and bandera.iloc[:5].sum() == 0 and pd.isna(bandera.iloc[6])
    assert limite < 1000


# ---------------------------------------------------------------------- listings
@pytest.fixture
def df_listings(cliente_mongo):
    with Extraccion(base_datos="airbnb_test", cliente=cliente_mongo) as ext:
        return ext.extraer_listings()


def test_listings_normaliza_precio_y_categoriza(df_listings):
    listings, hosts, amenities = Transformacion().transformar_listings(df_listings)
    por_id = listings.set_index("listing_id")
    assert por_id.loc[1, "price"] == pytest.approx(284294.01)
    assert por_id.loc[1, "rango_precio"] == "Alto"          # 284.294 COP: entre 230k y 500k
    assert por_id.loc[3, "rango_precio"] == "Premium"
    assert por_id.loc[2, "rango_precio"] == "Económico"
    assert por_id.loc[7, "rango_precio"] == "Sin precio" and pd.isna(por_id.loc[7, "price"])
    assert por_id.loc[8, "precio_atipico"] == 1 and por_id.loc[1, "precio_atipico"] == 0


def test_estadia_minima_mayor_a_30_noches_se_marca_sin_eliminar(df_listings):
    listings, _, _ = Transformacion().transformar_listings(df_listings)
    por_id = listings.set_index("listing_id")
    assert por_id.loc[4, "minimo_noches_atipico"] == 1 and por_id.loc[2, "minimo_noches_atipico"] == 0
    assert len(listings) == 8


def test_listings_convierte_booleanos_y_fechas_y_deriva_bano(df_listings):
    listings, _, _ = Transformacion().transformar_listings(df_listings)
    por_id = listings.set_index("listing_id")
    assert por_id.loc[1, "host_id"] in (100, 101)
    assert por_id.loc[2, "last_scraped"] == "2026-06-22" and por_id.loc[2, "first_review"] == "2020-01-15"
    assert por_id.loc[1, "bano_compartido"] == 1 and por_id.loc[2, "bano_compartido"] == 0
    assert por_id.loc[2, "description"] == "Texto con saltos"


def test_listings_desanida_amenities_y_hosts(df_listings):
    listings, hosts, amenities = Transformacion().transformar_listings(df_listings)
    assert "amenities" not in listings.columns
    assert set(amenities["amenity"]) == {"Wifi", "Kitchen", "Children’s books and toys"}
    assert amenities.duplicated().sum() == 0                       # 'Wifi' repetido se deduplica
    assert listings.set_index("listing_id").loc[1, "n_amenities"] == 3
    assert listings.set_index("listing_id").loc[6, "n_amenities"] == 0
    # el anfitrión sale a su propia tabla y deja solo host_id en listings
    assert sorted(hosts["host_id"]) == [100, 101]
    assert not any(c.startswith("host_") and c != "host_id" for c in listings.columns)
    assert "host_is_superhost" in hosts.columns and hosts["host_is_superhost"].isin([0, 1]).all()


def test_listings_elimina_duplicados_por_llave(df_listings):
    duplicado = pd.concat([df_listings, df_listings.iloc[[0]]], ignore_index=True)
    listings, _, _ = Transformacion().transformar_listings(duplicado)
    assert len(listings) == 8


def test_listings_puede_descartar_sin_precio(df_listings):
    listings, _, amenities = Transformacion(eliminar_sin_precio=True).transformar_listings(df_listings)
    assert 7 not in set(listings["listing_id"]) and 7 not in set(amenities["listing_id"])


def test_listings_sin_columna_id_falla_con_mensaje():
    with pytest.raises(ErrorTransformacion, match="id"):
        Transformacion().transformar_listings(pd.DataFrame({"x": [1]}))


def test_columnas_100_por_ciento_nulas_se_descartan(df_listings):
    df = df_listings.assign(columna_vacia=np.nan)
    listings, _, _ = Transformacion().transformar_listings(df)
    assert "columna_vacia" not in listings.columns


def test_no_asume_que_existan_todas_las_columnas():
    df = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})   # sin price, amenities, host_id...
    listings, hosts, amenities = Transformacion().transformar_listings(df)
    assert len(listings) == 2 and hosts.empty and amenities.empty


# ----------------------------------------------------------------------- reviews
def test_reviews_limpieza_completa(cliente_mongo, df_listings):
    with Extraccion(base_datos="airbnb_test", cliente=cliente_mongo) as ext:
        crudo = ext.extraer_reviews()
    reviews = Transformacion().transformar_reviews(crudo, pd.Series([1, 2, 3]))
    # 6 filas: -1 duplicada, -1 fecha inválida, -1 huérfana (listing 99)
    assert sorted(reviews["review_id"]) == [10, 11, 12]
    r = reviews.set_index("review_id")
    assert r.loc[10, "fecha"] == "2021-03-05" and r.loc[10, "anio"] == 2021 and r.loc[10, "trimestre"] == 1
    assert r.loc[11, "mes"] == 12 and r.loc[11, "dia"] == 31 and r.loc[11, "trimestre"] == 4
    assert r.loc[10, "comentario"] == "Muy bueno. Volvería" and r.loc[10, "reviewer_name"] == "Ana"
    assert r.loc[11, "sin_comentario"] == 1 and r.loc[11, "longitud_comentario"] == 0
    assert r.loc[10, "sin_comentario"] == 0


# ---------------------------------------------------------------------- calendar
def test_calendario_mensual_derivadas(cliente_mongo):
    with Extraccion(base_datos="airbnb_test", cliente=cliente_mongo) as ext:
        mensual = ext.extraer_calendario_mensual()
    cal = Transformacion().transformar_calendario_mensual(mensual, pd.Series([1, 2]))
    fila = cal[(cal.listing_id == 1) & (cal.fecha_mes == "2026-06-01")].iloc[0]
    assert fila.anio == 2026 and fila.mes == 6 and fila.trimestre == 2
    assert fila.dias_no_disponibles == 1 and fila.pct_disponibilidad == pytest.approx(66.67)
    assert fila.mes_completo == 0                         # solo 3 de 30 días registrados


def test_calendar_diario_trata_centinela_de_maximum_nights(cliente_mongo):
    with Extraccion(base_datos="airbnb_test", cliente=cliente_mongo) as ext:
        diario = ext.extraer_calendar()
    cal = Transformacion().transformar_calendar_diario(diario)
    assert cal["maximum_nights"].isna().sum() == 1
    assert set(cal["disponible"].dropna()) == {0, 1} and {"anio", "mes", "dia", "trimestre"} <= set(cal.columns)


# ---------------------------------------------------------------------- conjunto
def test_ejecutar_devuelve_todas_las_tablas_y_registra_antes_despues(cliente_mongo, log_aislado):
    with Extraccion(base_datos="airbnb_test", cliente=cliente_mongo) as ext:
        fuentes = ext.extraer_todo()
    tablas = Transformacion().ejecutar(fuentes)
    assert set(tablas) == {"listings", "hosts", "listing_amenities", "reviews", "calendario_mensual"}
    texto = next(log_aislado.glob("log_*.txt")).read_text(encoding="utf-8")
    assert "registros antes" in texto and "WARNING" in texto and "Inicio de la transformación" in texto
