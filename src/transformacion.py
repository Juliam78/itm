"""Transformación: limpia, normaliza y enriquece los DataFrames extraídos de MongoDB.

Requisito del taller (sección 3): una clase ``Transformacion`` que realice como
mínimo limpieza de nulos y duplicados, normalización de precios, fechas en
YYYY-MM-DD, variables derivadas de la fecha, categorización de precios,
tratamiento de campos anidados y que registre en el log las transformaciones y
los conteos antes/después.

Técnicas tomadas del repositorio de ejemplo del profesor (src/transformacion.py):
funciones pequeñas por tipo de limpieza, ``pd.to_numeric(errors="coerce")``,
``pd.to_datetime(errors="coerce")``, deduplicación por llave de negocio y log de
filas. Lo específico de Airbnb se implementa aquí desde cero.

Principio general: NO se asume que todas las columnas existan. Cada paso revisa
qué columnas hay en el DataFrame recibido (los documentos de MongoDB pueden
omitir campos vacíos) y registra un WARNING cuando algo esperado falta.
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from src.config import FACTOR_IQR_ATIPICOS, PRECIO_CORTES, PRECIO_ETIQUETAS, UMBRAL_MINIMO_NOCHES
from src.logger_etl import obtener_logger

log = obtener_logger("transformacion")

TEXTO_SIN_INFO = "Sin información"

# --- Catálogos de columnas (se aplican solo a las que existan) ----------------------
FECHAS_LISTINGS = [
    "last_scraped", "first_review", "last_review", "calendar_last_scraped",
    "host_since", "price_quote_checkin_date", "price_quote_checkout_date",
]
BOOLEANAS_LISTINGS = [
    "host_is_superhost", "host_has_profile_pic", "host_identity_verified",
    "has_availability", "instant_bookable",
]
TEXTOS_LISTINGS = [
    "name", "description", "neighborhood_overview", "host_about", "host_name",
    "host_location", "bathrooms_text", "property_type", "room_type", "neighbourhood_cleansed",
]
# Texto libre descriptivo: si falta se rellena con una etiqueta explícita.
TEXTOS_RELLENAR = ["description", "neighborhood_overview", "host_about", "host_location"]
# Columnas que describen al anfitrión y se mueven a la tabla ``hosts``.
PREFIJOS_HOST = ("host_", "hosts_")
# Payload JSON crudo y redundante: price_quote_total_price / price_per_night ya lo extraen.
COLUMNAS_DESCARTADAS_LISTINGS = ["price_quote_raw"]


class ErrorTransformacion(Exception):
    """Error irrecuperable durante la transformación (p. ej. falta la llave de negocio)."""


# =====================================================================================
# Funciones auxiliares (puras, fáciles de probar)
# =====================================================================================
def limpiar_precio(serie: pd.Series) -> pd.Series:
    """Convierte textos como ``'$284,294.01'`` en número (284294.01).

    Se eliminan todos los caracteres que no sean dígitos, punto o signo menos.
    Supuesto verificado en los datos: el punto es separador decimal y la coma
    separa miles (formato en inglés). Si apareciera otro formato quedaría NaN y
    el llamador lo registra como advertencia.
    """
    texto = serie.astype("string").str.replace(r"[^0-9.\-]", "", regex=True)
    return pd.to_numeric(texto, errors="coerce").astype("float64")


def a_fecha(serie: pd.Series) -> pd.Series:
    """Convierte a datetime64 (valores inválidos → NaT)."""
    return pd.to_datetime(serie, errors="coerce")


def fecha_iso(fechas: pd.Series) -> pd.Series:
    """Formatea un datetime como texto estándar ``YYYY-MM-DD``."""
    return fechas.dt.strftime("%Y-%m-%d")


def a_booleano(serie: pd.Series) -> pd.Series:
    """Convierte 't'/'f' (y variantes) a 1/0 con soporte de nulos (Int64)."""
    mapa = {"t": 1, "true": 1, "1": 1, "yes": 1, "si": 1, "f": 0, "false": 0, "0": 0, "no": 0}
    texto = serie.astype("string").str.strip().str.lower()
    return texto.map(mapa).astype("Int64")


_RE_BR = re.compile(r"<\s*br\s*/?\s*>", flags=re.IGNORECASE)
_RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_RE_ESPACIOS = re.compile(r"\s+")


def limpiar_texto(serie: pd.Series) -> pd.Series:
    """Estandariza texto libre: quita etiquetas ``<br/>``, caracteres de control, espacios repetidos.

    Se detectó que ~69 mil reseñas contienen ``<br/>`` y ~800 contienen ``\\r``;
    además, los caracteres de control hacen fallar la escritura a XLSX (openpyxl).
    """
    texto = serie.astype("string")
    texto = texto.str.replace(_RE_BR, " ", regex=True)
    texto = texto.str.replace(_RE_CONTROL, "", regex=True)
    texto = texto.str.replace(_RE_ESPACIOS, " ", regex=True).str.strip()
    return texto


def marcar_atipicos_iqr(serie: pd.Series, factor: float = FACTOR_IQR_ATIPICOS) -> tuple[pd.Series, float]:
    """Marca como atípicos los valores por encima de ``Q3 + factor * IQR``.

    Devuelve ``(bandera Int64, límite_superior)``. Los valores no se eliminan:
    en Airbnb un precio extremo puede ser un anuncio real (propiedad de lujo) o
    un error de captura, y esa decisión corresponde al análisis, no al ETL.
    """
    q1, q3 = serie.quantile(0.25), serie.quantile(0.75)
    limite = q3 + factor * (q3 - q1)
    bandera = (serie > limite).astype("Int64").where(serie.notna())
    return bandera, float(limite) if pd.notna(limite) else float("nan")


def parsear_amenities(valor) -> tuple[list[str], bool]:
    """Convierte el campo ``amenities`` en una lista de servicios.

    En el dataset llega como texto JSON (``'["Wifi", "Kitchen", ...]'``).
    Devuelve ``(lista, ok)``; ``ok=False`` indica que hubo que usar el método de
    respaldo (separar por comas) porque el JSON no era válido.
    """
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return [], True
    if isinstance(valor, (list, tuple, np.ndarray)):
        elementos, ok = list(valor), True
    else:
        try:
            elementos, ok = json.loads(valor), True
            if not isinstance(elementos, list):
                raise ValueError("amenities no es una lista")
        except (ValueError, TypeError):
            limpio = str(valor).strip().strip("[]{}")
            elementos = [parte.strip().strip("\"'") for parte in limpio.split(",")]
            ok = False
    vistos: dict[str, None] = {}
    for elemento in elementos:
        texto = _RE_ESPACIOS.sub(" ", str(elemento)).strip()
        if texto:
            vistos[texto] = None  # dict conserva orden y elimina repetidos
    return list(vistos), ok


# =====================================================================================
# Clase principal
# =====================================================================================
class Transformacion:
    """Transforma las fuentes extraídas y produce los DataFrames listos para cargar.

    Parameters
    ----------
    eliminar_sin_precio:
        Si es True se descartan los anuncios sin precio (≈1 % en junio 2026). Por
        defecto se conservan con ``rango_precio='Sin precio'`` para no perder
        información de oferta; el análisis de precios debe filtrarlos.
    cortes_precio, etiquetas_precio:
        Límites (COP) y nombres de los rangos de precio.
    """

    def __init__(
        self,
        eliminar_sin_precio: bool = False,
        cortes_precio: list[float] | None = None,
        etiquetas_precio: list[str] | None = None,
    ) -> None:
        self.eliminar_sin_precio = eliminar_sin_precio
        self.cortes_precio = list(cortes_precio or PRECIO_CORTES)
        self.etiquetas_precio = list(etiquetas_precio or PRECIO_ETIQUETAS)
        if len(self.cortes_precio) != len(self.etiquetas_precio) + 1:
            raise ValueError("Debe haber un corte más que etiquetas de precio")

    # ------------------------------------------------------------------ utilidades
    @staticmethod
    def _conteo(etapa: str, antes: int, despues: int) -> None:
        nivel = log.info if antes == despues else log.warning
        nivel("%s: %s registros antes, %s después (%s eliminados)",
              etapa, f"{antes:,}", f"{despues:,}", f"{antes - despues:,}")

    @staticmethod
    def _existentes(df: pd.DataFrame, columnas: list[str]) -> list[str]:
        return [c for c in columnas if c in df.columns]

    @staticmethod
    def _derivar_calendario(fechas: pd.Series) -> pd.DataFrame:
        """Variables derivadas de una fecha: año, mes, día y trimestre."""
        return pd.DataFrame({
            "anio": fechas.dt.year.astype("Int64"),
            "mes": fechas.dt.month.astype("Int64"),
            "dia": fechas.dt.day.astype("Int64"),
            "trimestre": fechas.dt.quarter.astype("Int64"),
        })

    # ================================================================== LISTINGS
    def transformar_listings(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Limpia ``Listings`` y devuelve ``(listings, hosts, listing_amenities)``.

        Transformaciones (todas justificadas con el perfil de los datos de junio 2026):

        1. ``id`` → ``listing_id`` (llave foránea consistente con Reviews/Calendar).
        2. Duplicados por llave de negocio (no hay en el dataset actual; se protege el ETL).
        3. Columnas 100 % nulas se descartan (13 de 90 en el dataset actual).
        4. ``price`` ("$284,294.01") → número; ``rango_precio`` y bandera ``precio_atipico``.
        5. ``minimum_nights`` atípico marcado; ``availability_365`` validado en 0–365.
        6. Fechas → YYYY-MM-DD; 't'/'f' → 1/0; texto estandarizado.
        7. ``amenities`` (JSON en texto) → tabla larga ``listing_amenities`` + ``n_amenities``.
        8. Columnas del anfitrión (``host_*``) → tabla ``hosts`` (un registro por anfitrión).
        """
        if df is None or df.empty:
            raise ErrorTransformacion("Listings llegó vacío: no hay nada que transformar")
        log.info("Transformación de Listings: %s filas, %s columnas de entrada", f"{len(df):,}", df.shape[1])
        listings = df.copy()
        inicial = len(listings)

        # 1. Llave de negocio
        if "id" in listings.columns:
            listings = listings.rename(columns={"id": "listing_id"})
        if "listing_id" not in listings.columns:
            raise ErrorTransformacion("Listings no tiene la columna 'id' (llave del anuncio)")
        sin_llave = listings["listing_id"].isna().sum()
        if sin_llave:
            log.warning("%s anuncios sin id se descartan", sin_llave)
            listings = listings.dropna(subset=["listing_id"])
        listings["listing_id"] = listings["listing_id"].astype("int64")

        # 2. Duplicados
        duplicados = int(listings.duplicated("listing_id").sum())
        if duplicados:
            log.warning("Se encontraron %s anuncios con listing_id repetido; se conserva el último", duplicados)
            listings = listings.drop_duplicates("listing_id", keep="last")
        else:
            log.info("Sin listing_id duplicados")
        self._conteo("Deduplicación de Listings", inicial, len(listings))

        # 3. Columnas totalmente nulas y payloads redundantes
        nulas = [c for c in listings.columns if listings[c].isna().all()]
        if nulas:
            log.info("Se descartan %s columnas 100%% nulas (sin información útil): %s", len(nulas), nulas)
            listings = listings.drop(columns=nulas)
        descartadas = self._existentes(listings, COLUMNAS_DESCARTADAS_LISTINGS)
        if descartadas:
            log.info("Se descartan columnas redundantes (payload JSON ya extraído en otras columnas): %s", descartadas)
            listings = listings.drop(columns=descartadas)

        # 4. Precio
        listings = self._normalizar_precio(listings)

        # 5. Rangos y atípicos de otras variables
        listings = self._validar_numericas(listings)

        # 6. Fechas, booleanos y texto
        for col in self._existentes(listings, FECHAS_LISTINGS):
            fechas = a_fecha(listings[col])
            invalidas = int(fechas.isna().sum() - listings[col].isna().sum())
            if invalidas:
                log.warning("%s: %s fechas no interpretables quedan nulas", col, invalidas)
            listings[col] = fecha_iso(fechas)
        log.info("Fechas convertidas a YYYY-MM-DD: %s", self._existentes(listings, FECHAS_LISTINGS))

        booleanas = self._existentes(listings, BOOLEANAS_LISTINGS)
        for col in booleanas:
            listings[col] = a_booleano(listings[col])
        if booleanas:
            log.info("Columnas t/f convertidas a 1/0: %s", booleanas)

        for col in self._existentes(listings, TEXTOS_LISTINGS):
            listings[col] = limpiar_texto(listings[col])
        for col in self._existentes(listings, TEXTOS_RELLENAR):
            nulos = int(listings[col].isna().sum())
            if nulos:
                listings[col] = listings[col].fillna(TEXTO_SIN_INFO)
                log.info("%s: %s nulos rellenados con '%s'", col, f"{nulos:,}", TEXTO_SIN_INFO)

        if "bathrooms_text" in listings.columns:
            # El número de baños ya está en 'bathrooms', pero 'shared/private' solo viene en el texto.
            compartido = listings["bathrooms_text"].str.contains("shared", case=False, na=False)
            listings["bano_compartido"] = compartido.astype("Int64").where(listings["bathrooms_text"].notna())
            log.info("Derivada 'bano_compartido' a partir de bathrooms_text")

        # 7. Anidados: amenities
        amenities = self._expandir_amenities(listings)
        if "amenities" in listings.columns:
            conteo = amenities.groupby("listing_id").size()
            listings["n_amenities"] = listings["listing_id"].map(conteo).fillna(0).astype("Int64")
            listings = listings.drop(columns=["amenities"])

        # 8. Anidados: anfitrión
        listings, hosts = self._separar_hosts(listings)

        # 9. Anuncios sin precio (opcional)
        if self.eliminar_sin_precio and "price" in listings.columns:
            antes = len(listings)
            listings = listings[listings["price"].notna()]
            self._conteo("Eliminación de anuncios sin precio", antes, len(listings))
            amenities = amenities[amenities["listing_id"].isin(listings["listing_id"])]

        listings = listings.reset_index(drop=True)
        log.info("Listings transformado: %s filas, %s columnas | hosts: %s filas | amenities: %s filas",
                 f"{len(listings):,}", listings.shape[1], f"{len(hosts):,}", f"{len(amenities):,}")
        return listings, hosts, amenities

    def _normalizar_precio(self, listings: pd.DataFrame) -> pd.DataFrame:
        """Convierte ``price`` a número y crea ``rango_precio`` y ``precio_atipico``."""
        if "price" not in listings.columns:
            log.warning("Listings no trae 'price': se omite la normalización de precios")
            return listings
        originales_no_nulos = int(listings["price"].notna().sum())
        listings["price"] = limpiar_precio(listings["price"])
        no_convertidos = originales_no_nulos - int(listings["price"].notna().sum())
        if no_convertidos:
            log.warning("%s precios no pudieron convertirse a número y quedan nulos", no_convertidos)
        sin_precio = int(listings["price"].isna().sum())
        log.info("Precio normalizado a número (símbolos '$' y ',' eliminados); %s anuncios sin precio", f"{sin_precio:,}")
        no_positivos = int((listings["price"] <= 0).sum())
        if no_positivos:
            log.warning("%s anuncios con precio <= 0; se dejan como nulos", no_positivos)
            listings.loc[listings["price"] <= 0, "price"] = np.nan

        rango = pd.cut(listings["price"], bins=self.cortes_precio, labels=self.etiquetas_precio, include_lowest=True)
        listings["rango_precio"] = rango.astype("string").fillna("Sin precio")
        bandera, limite = marcar_atipicos_iqr(listings["price"])
        listings["precio_atipico"] = bandera
        log.info("Categorización por rangos %s; %s precios atípicos marcados (> %s COP, Q3+%.0f*IQR), no eliminados",
                 self.etiquetas_precio, f"{int(bandera.fillna(0).sum()):,}", f"{limite:,.0f}", FACTOR_IQR_ATIPICOS)
        return listings

    @staticmethod
    def _validar_numericas(listings: pd.DataFrame) -> pd.DataFrame:
        """Marca estadías mínimas > 30 noches y valida que ``availability_365`` esté en 0–365."""
        if "minimum_nights" in listings.columns:
            # Regla de negocio (no IQR): ver comentario de UMBRAL_MINIMO_NOCHES en config.py.
            largas = listings["minimum_nights"] > UMBRAL_MINIMO_NOCHES
            listings["minimo_noches_atipico"] = largas.astype("Int64").where(listings["minimum_nights"].notna())
            log.info("minimum_nights: %s anuncios con estadía mínima > %s noches marcados (no eliminados)",
                     int(largas.sum()), UMBRAL_MINIMO_NOCHES)
        if "availability_365" in listings.columns:
            fuera = int(((listings["availability_365"] < 0) | (listings["availability_365"] > 365)).sum())
            if fuera:
                log.warning("availability_365: %s valores fuera de 0-365 quedan nulos", fuera)
                listings.loc[(listings["availability_365"] < 0) | (listings["availability_365"] > 365),
                             "availability_365"] = np.nan
            else:
                log.info("availability_365 validado: todos los valores están entre 0 y 365")
        return listings

    @staticmethod
    def _expandir_amenities(listings: pd.DataFrame) -> pd.DataFrame:
        """Desanida ``amenities`` en una tabla larga ``(listing_id, amenity)``."""
        if "amenities" not in listings.columns:
            log.warning("Listings no trae 'amenities': no se genera la tabla de servicios")
            return pd.DataFrame({"listing_id": pd.Series(dtype="int64"), "amenity": pd.Series(dtype="string")})
        ids: list[int] = []
        servicios: list[str] = []
        fallbacks = 0
        for listing_id, valor in zip(listings["listing_id"], listings["amenities"]):
            lista, ok = parsear_amenities(valor)
            fallbacks += not ok
            ids.extend([listing_id] * len(lista))
            servicios.extend(lista)
        if fallbacks:
            log.warning("%s anuncios con amenities que no eran JSON válido (se usó separación por comas)", fallbacks)
        tabla = pd.DataFrame({"listing_id": ids, "amenity": servicios})
        tabla["amenity"] = tabla["amenity"].astype("string")
        log.info("amenities desanidado: %s relaciones anuncio-servicio, %s servicios distintos",
                 f"{len(tabla):,}", f"{tabla['amenity'].nunique():,}")
        return tabla

    @staticmethod
    def _separar_hosts(listings: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Mueve las columnas del anfitrión a ``hosts`` (1 fila por ``host_id``)."""
        if "host_id" not in listings.columns:
            log.warning("Listings no trae 'host_id': no se genera la tabla hosts")
            return listings, pd.DataFrame()
        columnas_host = [c for c in listings.columns if c.startswith(PREFIJOS_HOST) and c != "host_id"]
        hosts = listings[["host_id"] + columnas_host].copy()
        inconsistentes = int((hosts.groupby("host_id").nunique(dropna=False).max(axis=1) > 1).sum())
        if inconsistentes:
            log.warning("%s anfitriones tienen datos distintos entre sus anuncios; se conserva el primero", inconsistentes)
        hosts = hosts.drop_duplicates("host_id", keep="first").reset_index(drop=True)
        listings = listings.drop(columns=columnas_host)
        log.info("Información del anfitrión separada: %s columnas movidas a 'hosts' (%s anfitriones)",
                 len(columnas_host), f"{len(hosts):,}")
        return listings, hosts

    # =================================================================== REVIEWS
    def transformar_reviews(self, df: pd.DataFrame, ids_listings: pd.Series | None = None) -> pd.DataFrame:
        """Limpia ``Reviews``.

        - ``id`` → ``review_id``; ``date`` → ``fecha`` (YYYY-MM-DD) + año/mes/día/trimestre.
        - Duplicados por ``review_id``; fechas inválidas descartadas.
        - ``comments`` → ``comentario`` sin ``<br/>`` ni caracteres de control; se agrega
          ``longitud_comentario`` y ``sin_comentario`` (191 reseñas sin texto en junio 2026).
        - Si se entrega ``ids_listings``, las reseñas de anuncios inexistentes se descartan
          (integridad referencial con la tabla ``listings``).
        """
        if df is None or df.empty:
            raise ErrorTransformacion("Reviews llegó vacío")
        log.info("Transformación de Reviews: %s filas, %s columnas de entrada", f"{len(df):,}", df.shape[1])
        reviews = df.rename(columns={"id": "review_id", "date": "fecha", "comments": "comentario"}).copy()
        for obligatoria in ("review_id", "listing_id", "fecha"):
            if obligatoria not in reviews.columns:
                raise ErrorTransformacion(f"Reviews no tiene la columna requerida '{obligatoria}'")
        inicial = len(reviews)

        duplicados = int(reviews.duplicated("review_id").sum())
        if duplicados:
            log.warning("%s reseñas con review_id repetido; se conserva la última", duplicados)
            reviews = reviews.drop_duplicates("review_id", keep="last")
        else:
            log.info("Sin review_id duplicados")

        fechas = a_fecha(reviews["fecha"])
        invalidas = int(fechas.isna().sum())
        if invalidas:
            log.warning("%s reseñas con fecha inválida o nula se descartan", invalidas)
        reviews = reviews[fechas.notna()].copy()
        fechas = fechas[fechas.notna()]
        reviews["fecha"] = fecha_iso(fechas)
        reviews = pd.concat([reviews, self._derivar_calendario(fechas)], axis=1)
        log.info("Reseñas: fecha en YYYY-MM-DD y variables derivadas anio, mes, dia, trimestre (rango %s a %s)",
                 reviews["fecha"].min(), reviews["fecha"].max())

        if ids_listings is not None:
            huerfanas = ~reviews["listing_id"].isin(ids_listings)
            if huerfanas.any():
                log.warning("%s reseñas pertenecen a anuncios que no existen en Listings; se descartan", int(huerfanas.sum()))
                reviews = reviews[~huerfanas]
            else:
                log.info("Integridad referencial verificada: todas las reseñas apuntan a un anuncio existente")

        if "comentario" not in reviews.columns:
            log.warning("Reviews no trae 'comments'; todas las reseñas quedan sin comentario")
            reviews["comentario"] = pd.NA
        nulos = int(reviews["comentario"].isna().sum())
        reviews["comentario"] = limpiar_texto(reviews["comentario"])
        reviews["sin_comentario"] = (reviews["comentario"].isna() | (reviews["comentario"] == "")).astype("Int64")
        reviews["longitud_comentario"] = reviews["comentario"].str.len().fillna(0).astype("Int64")
        log.info("Comentarios estandarizados (etiquetas <br/> y espacios); %s reseñas sin comentario conservadas con bandera", f"{nulos:,}")
        if "reviewer_name" in reviews.columns:
            reviews["reviewer_name"] = limpiar_texto(reviews["reviewer_name"])

        orden = ["review_id", "listing_id", "fecha", "anio", "mes", "dia", "trimestre",
                 "reviewer_id", "reviewer_name", "comentario", "longitud_comentario", "sin_comentario"]
        reviews = reviews[[c for c in orden if c in reviews.columns]].reset_index(drop=True)
        self._conteo("Limpieza de Reviews", inicial, len(reviews))
        return reviews

    # ================================================================== CALENDAR
    def transformar_calendario_mensual(self, df: pd.DataFrame, ids_listings: pd.Series | None = None) -> pd.DataFrame:
        """Transforma el calendario agregado por (anuncio, mes) que entrega ``Extraccion``.

        Agrega ``fecha_mes`` (YYYY-MM-01), año/mes/trimestre, ``dias_no_disponibles``,
        ``pct_disponibilidad`` y ``mes_completo`` (el primer y el último mes del
        dataset son parciales: el calendario va del 2026-06-21 al 2027-06-21).
        """
        if df is None or df.empty:
            raise ErrorTransformacion("El calendario mensual llegó vacío")
        log.info("Transformación de Calendar (mensual): %s filas de entrada", f"{len(df):,}")
        cal = df.copy()
        inicial = len(cal)
        cal = cal.drop_duplicates(["listing_id", "mes"], keep="last")
        self._conteo("Deduplicación de calendario mensual", inicial, len(cal))

        fechas = a_fecha(cal["mes"].astype("string") + "-01")
        invalidas = int(fechas.isna().sum())
        if invalidas:
            log.warning("%s filas con mes inválido se descartan", invalidas)
            cal, fechas = cal[fechas.notna()].copy(), fechas[fechas.notna()]
        if ids_listings is not None:
            huerfanas = ~cal["listing_id"].isin(ids_listings)
            if huerfanas.any():
                log.warning("%s filas de calendario con anuncios inexistentes se descartan", int(huerfanas.sum()))
                cal, fechas = cal[~huerfanas].copy(), fechas[~huerfanas]

        cal["fecha_mes"] = fecha_iso(fechas)
        derivadas = self._derivar_calendario(fechas).drop(columns=["dia"])
        cal = pd.concat([cal.drop(columns=["mes"]), derivadas], axis=1)
        cal["dias_disponibles"] = cal["dias_disponibles"].astype("int64")
        cal["dias_no_disponibles"] = (cal["dias_registrados"] - cal["dias_disponibles"]).astype("int64")
        cal["pct_disponibilidad"] = (100 * cal["dias_disponibles"] / cal["dias_registrados"]).round(2)
        cal["minimo_noches_promedio"] = cal["minimo_noches_promedio"].round(2)
        cal["mes_completo"] = (cal["dias_registrados"] >= fechas.dt.days_in_month.values).astype("Int64")
        parciales = int((cal["mes_completo"] == 0).sum())
        log.info("Calendario mensual: %s filas; %s corresponden a meses parciales (bordes del rango)", f"{len(cal):,}", f"{parciales:,}")

        orden = ["listing_id", "fecha_mes", "anio", "mes", "trimestre", "dias_registrados", "dias_disponibles",
                 "dias_no_disponibles", "pct_disponibilidad", "minimo_noches_promedio", "mes_completo"]
        return cal[[c for c in orden if c in cal.columns]].sort_values(["listing_id", "fecha_mes"], ignore_index=True)

    def transformar_calendar_diario(self, df: pd.DataFrame, ids_listings: pd.Series | None = None) -> pd.DataFrame:
        """Transforma Calendar a nivel diario (úsese con muestras o con memoria suficiente).

        ``available`` ('t'/'f') → ``disponible`` (1/0); ``date`` → ``fecha`` + año/mes/día/trimestre;
        ``maximum_nights`` con el valor centinela 2147483647 (límite de int32 usado por Airbnb
        para "sin tope") se pasa a nulo.
        """
        if df is None or df.empty:
            raise ErrorTransformacion("Calendar llegó vacío")
        log.info("Transformación de Calendar (diario): %s filas de entrada", f"{len(df):,}")
        cal = df.rename(columns={"date": "fecha", "available": "disponible"}).copy()
        inicial = len(cal)
        cal = cal.drop_duplicates(["listing_id", "fecha"], keep="last")
        self._conteo("Deduplicación de Calendar diario", inicial, len(cal))

        fechas = a_fecha(cal["fecha"])
        if fechas.isna().any():
            log.warning("%s filas con fecha inválida se descartan", int(fechas.isna().sum()))
            cal, fechas = cal[fechas.notna()].copy(), fechas[fechas.notna()]
        cal["fecha"] = fecha_iso(fechas)
        cal = pd.concat([cal, self._derivar_calendario(fechas)], axis=1)
        cal["dia_semana"] = fechas.dt.dayofweek.astype("Int64")
        if "disponible" in cal.columns:
            cal["disponible"] = a_booleano(cal["disponible"])
        if "maximum_nights" in cal.columns:
            centinela = cal["maximum_nights"] > 3650
            if centinela.any():
                log.warning("maximum_nights: %s valores > 3650 (centinela tipo int32) pasan a nulo", f"{int(centinela.sum()):,}")
                cal.loc[centinela, "maximum_nights"] = np.nan
        if ids_listings is not None:
            huerfanas = ~cal["listing_id"].isin(ids_listings)
            if huerfanas.any():
                log.warning("%s filas con anuncios inexistentes se descartan", int(huerfanas.sum()))
                cal = cal[~huerfanas]
        return cal.reset_index(drop=True)

    # ================================================================ ORQUESTADOR
    def ejecutar(self, fuentes: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """Aplica todas las transformaciones y devuelve las tablas listas para cargar.

        Claves de ``fuentes`` esperadas: ``listings``, ``reviews`` y ``calendar_mensual``
        (o ``calendar`` si se extrajo el calendario diario completo).
        Tablas devueltas: ``listings``, ``hosts``, ``listing_amenities``, ``reviews`` y
        ``calendario_mensual`` (o ``calendar``).
        """
        log.info("=== Inicio de la transformación ===")
        listings, hosts, amenities = self.transformar_listings(fuentes["listings"])
        ids = listings["listing_id"]
        tablas = {"listings": listings, "hosts": hosts, "listing_amenities": amenities}
        tablas["reviews"] = self.transformar_reviews(fuentes["reviews"], ids)
        if "calendar_mensual" in fuentes:
            tablas["calendario_mensual"] = self.transformar_calendario_mensual(fuentes["calendar_mensual"], ids)
        elif "calendar" in fuentes:
            tablas["calendar"] = self.transformar_calendar_diario(fuentes["calendar"], ids)
        else:
            log.warning("No se recibió Calendar: la salida no incluye disponibilidad")
        tablas = {nombre: df for nombre, df in tablas.items() if df is not None and not df.empty}
        resumen = ", ".join(f"{n}={len(d):,}" for n, d in tablas.items())
        log.info("=== Fin de la transformación: %s ===", resumen)
        return tablas
