"""Carga: escribe los DataFrames transformados en SQLite y los exporta a XLSX.

Requisito del taller (sección 4): una clase ``Carga`` que inserte los datos en
una base SQLite nueva, exporte uno o varios XLSX, verifique que los registros se
cargaron correctamente y registre los eventos principales en el log.

Técnicas tomadas del repositorio de ejemplo del profesor (src/carga.py):
``sqlite3.connect`` + ``DataFrame.to_sql(if_exists="replace", index=False)`` y
logging del resultado. Lo nuevo: carga por lotes, índices únicos como control de
integridad, verificación de conteos y exportación XLSX con división de hojas.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pandas as pd
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from src.config import SALIDA_DIR, SQLITE_PATH
from src.logger_etl import obtener_logger

log = obtener_logger("carga")

# Límite de filas de datos por hoja en Excel (1.048.576 menos la fila de encabezado).
MAX_FILAS_HOJA = 1_048_575

# Plan de exportación por defecto: archivo → tablas (una hoja por tabla).
PLAN_XLSX = {
    "airbnb_listings.xlsx": ["listings", "hosts"],
    "airbnb_calendario_mensual.xlsx": ["calendario_mensual"],
    "airbnb_reviews.xlsx": ["reviews"],
    "airbnb_amenities.xlsx": ["listing_amenities"],
}
# Columnas que NO se exportan a XLSX (siguen completas en SQLite): el texto de 527 mil
# reseñas vuelve el archivo enorme y lento sin aportar a una hoja de cálculo.
EXCLUIR_EN_XLSX = {"reviews": ["comentario"]}

# Llave única de cada tabla: sirve de control de integridad y acelera los JOIN.
INDICES_UNICOS = {
    "listings": ["listing_id"],
    "hosts": ["host_id"],
    "reviews": ["review_id"],
    "calendario_mensual": ["listing_id", "fecha_mes"],
    "listing_amenities": ["listing_id", "amenity"],
}
INDICES_SIMPLES = {"reviews": ["listing_id"], "listings": ["host_id"]}


class ErrorCarga(Exception):
    """Error al cargar o verificar los datos en SQLite o al exportar a XLSX."""


class Carga:
    """Carga los datos transformados a SQLite y los exporta a XLSX."""

    def __init__(self, ruta_sqlite: Path | str = SQLITE_PATH, dir_xlsx: Path | str = SALIDA_DIR) -> None:
        self.ruta_sqlite = Path(ruta_sqlite)
        self.dir_xlsx = Path(dir_xlsx)

    # ------------------------------------------------------------------- SQLite
    def cargar_sqlite(self, tablas: dict[str, pd.DataFrame], if_exists: str = "replace", tamano_lote: int = 50_000) -> None:
        """Inserta cada DataFrame como una tabla de SQLite y crea los índices.

        ``if_exists="replace"`` hace la ejecución idempotente: volver a correr el ETL
        reconstruye las tablas sin duplicar registros.
        """
        self.ruta_sqlite.parent.mkdir(parents=True, exist_ok=True)
        log.info("Carga a SQLite: %s (%s tablas)", self.ruta_sqlite, len(tablas))
        try:
            with sqlite3.connect(self.ruta_sqlite) as conexion:
                for nombre, df in tablas.items():
                    inicio = time.perf_counter()
                    df.to_sql(nombre, conexion, if_exists=if_exists, index=False, chunksize=tamano_lote)
                    log.info("Tabla '%s' cargada: %s filas, %s columnas (%.1f s)",
                             nombre, f"{len(df):,}", df.shape[1], time.perf_counter() - inicio)
                self._crear_indices(conexion, tablas)
        except (sqlite3.Error, ValueError) as error:
            log.error("Error cargando datos en SQLite: %s", error)
            raise ErrorCarga(f"Falló la carga a SQLite: {error}") from error

    @staticmethod
    def _crear_indices(conexion: sqlite3.Connection, tablas: dict[str, pd.DataFrame]) -> None:
        """Crea índices únicos y simples. Un índice único fallido delata duplicados no resueltos."""
        for tabla, columnas in INDICES_UNICOS.items():
            if tabla in tablas and all(c in tablas[tabla].columns for c in columnas):
                conexion.execute(
                    f'CREATE UNIQUE INDEX IF NOT EXISTS ux_{tabla} ON "{tabla}" ({", ".join(columnas)})'
                )
        for tabla, columnas in INDICES_SIMPLES.items():
            for columna in columnas:
                if tabla in tablas and columna in tablas[tabla].columns:
                    conexion.execute(f'CREATE INDEX IF NOT EXISTS ix_{tabla}_{columna} ON "{tabla}" ({columna})')
        log.info("Índices creados (únicos por llave de negocio y de búsqueda por listing_id/host_id)")

    def verificar_carga(self, tablas: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Compara filas esperadas (DataFrame) con filas guardadas (SQLite).

        Devuelve un DataFrame con ``tabla, esperado, cargado, ok``. Registra INFO si
        coinciden y ERROR si no. Lanza ``ErrorCarga`` si alguna tabla no coincide.
        """
        resultados = []
        with sqlite3.connect(self.ruta_sqlite) as conexion:
            existentes = {f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for nombre, df in tablas.items():
                if nombre not in existentes:
                    cargado = -1
                else:
                    cargado = conexion.execute(f'SELECT COUNT(*) FROM "{nombre}"').fetchone()[0]
                ok = cargado == len(df)
                resultados.append({"tabla": nombre, "esperado": len(df), "cargado": cargado, "ok": ok})
                if ok:
                    log.info("Verificación OK: '%s' tiene %s filas, igual a lo transformado", nombre, f"{cargado:,}")
                else:
                    log.error("Verificación FALLIDA: '%s' esperado=%s cargado=%s", nombre, f"{len(df):,}", cargado)
        reporte = pd.DataFrame(resultados)
        if not reporte["ok"].all():
            raise ErrorCarga("La verificación de la carga encontró diferencias:\n" + reporte.to_string(index=False))
        return reporte

    # --------------------------------------------------------------------- XLSX
    def exportar_xlsx(
        self,
        tablas: dict[str, pd.DataFrame],
        plan: dict[str, list[str]] | None = None,
        excluir_columnas: dict[str, list[str]] | None = None,
    ) -> list[Path]:
        """Exporta las tablas a uno o varios archivos XLSX (una hoja por tabla).

        - ``plan``: ``{archivo.xlsx: [tablas]}``; por defecto :data:`PLAN_XLSX`.
        - ``excluir_columnas``: columnas que se omiten en Excel; por defecto :data:`EXCLUIR_EN_XLSX`.
        - Si una tabla supera el límite de Excel se divide en hojas ``nombre_1``, ``nombre_2``…
        """
        plan = plan or PLAN_XLSX
        excluir = EXCLUIR_EN_XLSX if excluir_columnas is None else excluir_columnas
        self.dir_xlsx.mkdir(parents=True, exist_ok=True)
        generados: list[Path] = []
        for archivo, nombres in plan.items():
            disponibles = [n for n in nombres if n in tablas]
            if not disponibles:
                log.warning("XLSX '%s' omitido: ninguna de sus tablas %s existe en esta ejecución", archivo, nombres)
                continue
            ruta = self.dir_xlsx / archivo
            inicio = time.perf_counter()
            try:
                with pd.ExcelWriter(ruta, engine="openpyxl") as escritor:
                    for nombre in disponibles:
                        df = self._preparar_para_excel(tablas[nombre], excluir.get(nombre, []))
                        for i, inicio_fila in enumerate(range(0, max(len(df), 1), MAX_FILAS_HOJA), start=1):
                            hoja = nombre if len(df) <= MAX_FILAS_HOJA else f"{nombre}_{i}"
                            df.iloc[inicio_fila:inicio_fila + MAX_FILAS_HOJA].to_excel(escritor, sheet_name=hoja[:31], index=False)
                            log.info("XLSX '%s', hoja '%s': %s filas", archivo, hoja[:31], f"{min(len(df) - inicio_fila, MAX_FILAS_HOJA):,}")
            except (OSError, ValueError) as error:
                log.error("Error exportando '%s': %s", archivo, error)
                raise ErrorCarga(f"Falló la exportación a {archivo}: {error}") from error
            log.info("XLSX generado: %s (%.1f MB, %.1f s)", ruta, ruta.stat().st_size / 1e6, time.perf_counter() - inicio)
            generados.append(ruta)
        return generados

    @staticmethod
    def _preparar_para_excel(df: pd.DataFrame, excluir: list[str]) -> pd.DataFrame:
        """Quita columnas excluidas, exporta los IDs como texto y elimina caracteres que Excel no admite."""
        preparado = df.drop(columns=[c for c in excluir if c in df.columns])
        # Excel guarda los números como double (15 dígitos): los IDs largos de Airbnb se exportan como texto.
        for col in preparado.columns:
            if col == "id" or col.endswith("_id"):
                if pd.api.types.is_float_dtype(preparado[col]):
                    # Un ID float (por nulos) se pasa a entero antes, para no exportar "123.0" o notación científica.
                    preparado[col] = preparado[col].astype("Int64")
                preparado[col] = preparado[col].astype("string")
        for col in preparado.columns:
            if pd.api.types.is_string_dtype(preparado[col]) or preparado[col].dtype == object:
                preparado[col] = preparado[col].astype("string").str.replace(ILLEGAL_CHARACTERS_RE, "", regex=True)
        return preparado

    # ------------------------------------------------------------------ conjunto
    def cargar_todo(self, tablas: dict[str, pd.DataFrame], exportar_xlsx: bool = True) -> dict:
        """SQLite + verificación + (opcional) XLSX. Devuelve un resumen de lo generado."""
        self.cargar_sqlite(tablas)
        reporte = self.verificar_carga(tablas)
        archivos = self.exportar_xlsx(tablas) if exportar_xlsx else []
        if not exportar_xlsx:
            log.warning("Exportación a XLSX omitida por solicitud")
        return {"sqlite": self.ruta_sqlite, "verificacion": reporte, "xlsx": archivos}
