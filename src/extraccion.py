"""Extracción: lee las colecciones de MongoDB local y las entrega como DataFrames.

Requisito del taller (sección 1.2): una clase ``Extraccion`` que conecte con la
base de datos, consulte cada colección, cargue los datos en DataFrames de pandas
y registre en el log la conexión y la cantidad de registros extraídos.

Técnicas tomadas del repositorio de ejemplo del profesor (src/extraccion.py):
``MongoClient`` con ``serverSelectionTimeoutMS``, proyección ``{"_id": 0}`` y
logging de filas extraídas. Lo que cambia aquí: se encapsula en una clase, se
valida la existencia de las colecciones y se lee por lotes porque Calendar tiene
~7 millones de documentos (el ejemplo del profesor usa ``list(find())``, que no
escala a ese volumen).
"""
from __future__ import annotations

import time
from typing import Any

import pandas as pd
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from src.config import COLECCIONES, MONGO_DATABASE, MONGO_TIMEOUT_MS, MONGO_URI
from src.logger_etl import obtener_logger

log = obtener_logger("extraccion")

# A partir de este número de documentos se advierte del consumo de memoria.
UMBRAL_ADVERTENCIA_MEMORIA = 1_000_000


class ErrorExtraccion(Exception):
    """Error al conectar con MongoDB o al leer sus colecciones."""


class Extraccion:
    """Extrae las colecciones Listings, Reviews y Calendar desde MongoDB.

    Parameters
    ----------
    uri, base_datos:
        Conexión a MongoDB. Por defecto salen de ``src.config`` (.env).
    colecciones:
        Mapa ``{"listings": "Listings", "reviews": "Reviews", "calendar": "Calendar"}``.
    cliente:
        Cliente ya creado (permite inyectar ``mongomock`` en las pruebas).
        Si es None se crea un ``MongoClient`` real al llamar a :meth:`conectar`.
    """

    def __init__(
        self,
        uri: str = MONGO_URI,
        base_datos: str = MONGO_DATABASE,
        colecciones: dict[str, str] | None = None,
        timeout_ms: int = MONGO_TIMEOUT_MS,
        cliente: Any = None,
    ) -> None:
        self.uri = uri
        self.nombre_bd = base_datos
        self.colecciones = dict(colecciones or COLECCIONES)
        self.timeout_ms = timeout_ms
        self.cliente = cliente
        self.db = None

    # ------------------------------------------------------------------ conexión
    def conectar(self) -> "Extraccion":
        """Abre la conexión y comprueba que el servidor responde (ping)."""
        try:
            if self.cliente is None:
                self.cliente = MongoClient(self.uri, serverSelectionTimeoutMS=self.timeout_ms)
            self.cliente.admin.command("ping")
            self.db = self.cliente[self.nombre_bd]
        except PyMongoError as error:
            log.error("No fue posible conectar con MongoDB (%s): %s", self._uri_segura(), error)
            raise ErrorExtraccion(
                "No hay conexión con MongoDB. Verifique que el servicio mongod esté "
                "iniciado y que MONGO_URI en el archivo .env sea correcto."
            ) from error
        log.info("Conexión exitosa con MongoDB (%s), base de datos '%s'", self._uri_segura(), self.nombre_bd)
        return self

    def cerrar(self) -> None:
        """Cierra la conexión."""
        if self.cliente is not None:
            self.cliente.close()
            log.info("Conexión con MongoDB cerrada")
        self.cliente = None
        self.db = None

    def __enter__(self) -> "Extraccion":
        return self.conectar()

    def __exit__(self, *_exc) -> None:
        self.cerrar()

    def _uri_segura(self) -> str:
        """URI sin credenciales, para que nunca queden usuario/clave en el log."""
        uri = str(self.uri)
        if "@" in uri and "://" in uri:
            esquema, resto = uri.split("://", 1)
            return f"{esquema}://***@{resto.rsplit('@', 1)[1]}"
        return uri

    def _requerir_conexion(self) -> None:
        if self.db is None:
            raise ErrorExtraccion("Primero debe llamar a conectar() (o usar 'with Extraccion() as ext').")

    # ---------------------------------------------------------------- validación
    def validar_colecciones(self) -> dict[str, int]:
        """Comprueba que existan las tres colecciones y que no estén vacías.

        Corresponde a la exigencia del enunciado de "validar que la información
        esté correctamente almacenada antes de iniciar el proceso ETL".
        Devuelve ``{clave: cantidad_de_documentos}``.
        """
        self._requerir_conexion()
        existentes = set(self.db.list_collection_names())
        conteos: dict[str, int] = {}
        faltantes = []
        for clave, nombre in self.colecciones.items():
            if nombre not in existentes:
                faltantes.append(nombre)
                log.error("La colección '%s' no existe en la base '%s'", nombre, self.nombre_bd)
                continue
            conteos[clave] = self.db[nombre].estimated_document_count()
            if conteos[clave] == 0:
                faltantes.append(nombre)
                log.error("La colección '%s' está vacía", nombre)
            else:
                log.info("Colección '%s': %s documentos", nombre, f"{conteos[clave]:,}")
        if faltantes:
            raise ErrorExtraccion(
                f"Colecciones ausentes o vacías: {faltantes}. Ejecute scripts/cargar_mongodb.py "
                "para importar los datasets antes de correr el ETL."
            )
        return conteos

    # ---------------------------------------------------------------- extracción
    def extraer_coleccion(
        self,
        clave: str,
        filtro: dict | None = None,
        proyeccion: dict | None = None,
        limite: int | None = None,
        tamano_lote: int = 50_000,
    ) -> pd.DataFrame:
        """Lee una colección y la devuelve como DataFrame.

        Parameters
        ----------
        clave:
            ``"listings"``, ``"reviews"`` o ``"calendar"`` (o el nombre literal de la colección).
        filtro, proyeccion:
            Filtro y proyección de MongoDB. El campo ``_id`` siempre se excluye.
        limite:
            Máximo de documentos a leer (útil para muestras en el EDA).
        tamano_lote:
            Los documentos se convierten a DataFrame por bloques para no duplicar
            memoria con una lista gigante de diccionarios.

        Notas
        -----
        Si los documentos no tienen exactamente los mismos campos (por ejemplo,
        porque la importación omitió valores vacíos), el DataFrame resultante
        contiene la unión de campos y rellena con NaN. Una columna que sea nula
        en todos los documentos simplemente no existirá en el DataFrame.
        """
        self._requerir_conexion()
        nombre = self.colecciones.get(clave, clave)
        inicio = time.perf_counter()
        coleccion = self.db[nombre]

        total = coleccion.estimated_document_count() if not filtro else None
        if limite is None and total and total > UMBRAL_ADVERTENCIA_MEMORIA:
            log.warning(
                "La colección '%s' tiene %s documentos; cargarla completa en pandas "
                "consume varios GB. Considere extraer_calendario_mensual() o usar 'limite'.",
                nombre, f"{total:,}",
            )

        cursor = coleccion.find(filtro or {}, {"_id": 0, **(proyeccion or {})})
        if limite:
            cursor = cursor.limit(int(limite))

        bloques: list[pd.DataFrame] = []
        lote: list[dict] = []
        try:
            for documento in cursor:
                lote.append(documento)
                if len(lote) >= tamano_lote:
                    bloques.append(pd.DataFrame(lote))
                    lote = []
            if lote:
                bloques.append(pd.DataFrame(lote))
        except PyMongoError as error:
            log.error("Fallo al leer la colección '%s': %s", nombre, error)
            raise ErrorExtraccion(f"No fue posible leer la colección '{nombre}'.") from error

        df = pd.concat(bloques, ignore_index=True) if bloques else pd.DataFrame()
        log.info(
            "Extracción de '%s': %s registros, %s columnas (%.1f s)",
            nombre, f"{len(df):,}", df.shape[1], time.perf_counter() - inicio,
        )
        if df.empty:
            log.warning("La extracción de '%s' devolvió 0 registros", nombre)
        return df

    def extraer_listings(self, **kwargs) -> pd.DataFrame:
        """Colección Listings completa (≈19 mil documentos, 90 campos en el dataset de junio 2026)."""
        return self.extraer_coleccion("listings", **kwargs)

    def extraer_reviews(self, **kwargs) -> pd.DataFrame:
        """Colección Reviews completa (≈528 mil documentos)."""
        return self.extraer_coleccion("reviews", **kwargs)

    def extraer_calendar(self, **kwargs) -> pd.DataFrame:
        """Colección Calendar a nivel diario (≈7 millones de documentos). Pesada: use 'limite' en exploración."""
        return self.extraer_coleccion("calendar", **kwargs)

    def extraer_calendario_mensual(self) -> pd.DataFrame:
        """Resume Calendar por (listing_id, mes) usando un pipeline de agregación en MongoDB.

        Decisión de diseño: en vez de traer 7 millones de filas diarias a pandas,
        el agrupamiento se hace en el servidor y solo viajan ~250 mil filas
        (≈19 mil anuncios x 13 meses). Sigue siendo "extraer una colección de
        MongoDB a un DataFrame": la fuente es MongoDB y el resultado es un DataFrame.

        Columnas devueltas: ``listing_id``, ``mes`` (YYYY-MM), ``dias_registrados``,
        ``dias_disponibles`` y ``minimo_noches_promedio``.
        """
        self._requerir_conexion()
        nombre = self.colecciones["calendar"]
        coleccion = self.db[nombre]
        inicio = time.perf_counter()

        muestra = coleccion.find_one({}, {"_id": 0, "date": 1})
        if muestra is None:
            log.warning("La colección '%s' está vacía; no hay nada que agregar", nombre)
            return pd.DataFrame()
        # La importación puede dejar 'date' como texto ISO (lo normal con CSV) o como Date de Mongo.
        if isinstance(muestra.get("date"), str):
            expresion_mes: Any = {"$substr": ["$date", 0, 7]}
        else:
            expresion_mes = {"$dateToString": {"format": "%Y-%m", "date": "$date"}}

        pipeline = [
            {
                "$group": {
                    "_id": {"listing_id": "$listing_id", "mes": expresion_mes},
                    "dias_registrados": {"$sum": 1},
                    "dias_disponibles": {
                        "$sum": {"$cond": [{"$in": ["$available", ["t", True]]}, 1, 0]}
                    },
                    "minimo_noches_promedio": {"$avg": "$minimum_nights"},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "listing_id": "$_id.listing_id",
                    "mes": "$_id.mes",
                    "dias_registrados": 1,
                    "dias_disponibles": 1,
                    "minimo_noches_promedio": 1,
                }
            },
        ]
        try:
            filas = list(coleccion.aggregate(pipeline, allowDiskUse=True))
        except PyMongoError as error:
            log.error("Fallo la agregación mensual de '%s': %s", nombre, error)
            raise ErrorExtraccion(f"No fue posible agregar la colección '{nombre}'.") from error

        df = pd.DataFrame(filas)
        if not df.empty:
            df = df.sort_values(["listing_id", "mes"], ignore_index=True)
        log.info(
            "Extracción agregada de '%s' (listing_id x mes): %s registros (%.1f s)",
            nombre, f"{len(df):,}", time.perf_counter() - inicio,
        )
        return df

    def extraer_todo(self, calendar: str = "mensual") -> dict[str, pd.DataFrame]:
        """Extrae las tres colecciones.

        ``calendar`` puede ser ``"mensual"`` (por defecto, agregado en MongoDB),
        ``"completo"`` (7 M de filas; requiere mucha memoria) u ``"omitir"``.
        Devuelve un diccionario con las claves ``listings``, ``reviews`` y
        ``calendar_mensual`` o ``calendar``.
        """
        if calendar not in {"mensual", "completo", "omitir"}:
            raise ValueError("calendar debe ser 'mensual', 'completo' u 'omitir'")
        self.validar_colecciones()
        fuentes = {
            "listings": self.extraer_listings(),
            "reviews": self.extraer_reviews(),
        }
        if calendar == "mensual":
            fuentes["calendar_mensual"] = self.extraer_calendario_mensual()
        elif calendar == "completo":
            fuentes["calendar"] = self.extraer_calendar()
        else:
            log.warning("Calendar omitido por solicitud: no se generará la tabla de disponibilidad")
        return fuentes
