# ETL Airbnb Bogotá (Taller 2 – Inteligencia de Negocios, ITM)

Proceso ETL automatizado en Python que **extrae desde MongoDB local** los datasets de Airbnb Bogotá
(`Listings`, `Reviews`, `Calendar`), los **transforma** con pandas y los **carga** en una base SQLite y en
archivos XLSX, registrando un archivo de log por ejecución.

> La extracción **nunca** lee los CSV: los `.csv.gz` solo se usan en `scripts/cargar_mongodb.py` para poblar MongoDB.

**Datos fuente:** Inside Airbnb, Bogotá, corte del 21 de junio de 2026
(`listings.csv.gz` 19 187 anuncios · `reviews.csv.gz` 527 731 reseñas · `calendar.csv.gz` 7 003 255 días).
Se descargan de `https://data.insideairbnb.com/colombia/dc/bogotá/2026-06-21/data/` y **no** se suben al repositorio.

## Estructura

```
etl_airbnb/
├── src/
│   ├── config.py           # configuración (.env), rutas, rangos de precio
│   ├── logger_etl.py       # logs: un archivo logs/log_YYYYMMDD_HHMM.txt por ejecución
│   ├── extraccion.py       # clase Extraccion  (MongoDB -> DataFrames)
│   ├── transformacion.py   # clase Transformacion (limpieza, normalización, derivadas)
│   ├── carga.py            # clase Carga (SQLite + verificación + XLSX)
│   └── pipeline.py         # orquestador: python -m src.pipeline
├── scripts/
│   ├── cargar_mongodb.py   # importa los .csv.gz a MongoDB y valida la importación
│   └── probar_conexion.py  # comprueba MongoDB y las 3 colecciones
├── notebooks/              # exploracion_airbnb.ipynb (EDA leyendo de MongoDB) + figuras/
├── tests/                  # pruebas con pytest (mongomock)
├── logs/  sqlite/  datos/{fuente,salida}/
├── requirements.txt  .env.example
```

## Instalación

Requisitos: Python 3.10+ y un MongoDB Community local en ejecución (`mongod`, puerto 27017 por defecto).

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Linux/macOS: cp .env.example .env   (ajustar si es necesario)
```

En Windows, si PowerShell no permite ejecutar `activate` ("la ejecución de scripts está deshabilitada"), no hace falta activarlo:
use `.venv\Scripts\python` en lugar de `python` en todos los comandos (por ejemplo `.venv\Scripts\python -m src.pipeline`).

## Ejecución

1. Copiar `listings.csv.gz`, `reviews.csv.gz` y `calendar.csv.gz` a `datos/fuente/`
   (también se aceptan los nombres `listings_csv.gz`, etc.).
2. Poblar MongoDB (una sola vez; tarda varios minutos por los ~7 millones de filas de Calendar):
   ```bash
   python scripts/cargar_mongodb.py
   python scripts/probar_conexion.py
   ```
3. Ejecutar el ETL:
   ```bash
   python -m src.pipeline                 # completo: SQLite + XLSX
   python -m src.pipeline --sin-xlsx      # solo SQLite
   python -m src.pipeline --calendar omitir
   ```
4. Revisar resultados: `sqlite/airbnb_bogota.db`, `datos/salida/*.xlsx` y `logs/log_*.txt`.
5. Exploración (EDA): `python -m jupyterlab` y abrir `notebooks/exploracion_airbnb.ipynb` (Run → Run All Cells).
   Las figuras quedan en `notebooks/figuras/`.

Pruebas automáticas: `pytest -q` (usan `mongomock`, no requieren MongoDB).

## Tablas generadas

| Tabla | Contenido | Granularidad |
|---|---|---|
| `listings` | anuncios limpios, precio numérico, `rango_precio`, banderas de atípicos | 1 fila por anuncio |
| `hosts` | datos del anfitrión (desanidado de listings) | 1 fila por anfitrión |
| `listing_amenities` | `amenities` desanidado | 1 fila por (anuncio, servicio) |
| `reviews` | reseñas con fecha ISO y año/mes/día/trimestre | 1 fila por reseña |
| `calendario_mensual` | disponibilidad de Calendar agregada en MongoDB | 1 fila por (anuncio, mes) |

## Integrantes y responsabilidades

| Integrante | Responsabilidad |
|---|---|
| Julian Macea Cardona | Código del ETL (`src/`: extracción, transformación, carga y logs), pruebas, notebook de exploración, README y publicación del repositorio |
| David Lopez Cano | Bases de datos: instalación y configuración de MongoDB, importación y validación de las colecciones `Listings`, `Reviews` y `Calendar`, y apoyo con la base SQLite de salida |

Los commits del repositorio se hicieron desde la cuenta de Julian; el trabajo de David sobre las bases de datos se integró en esos commits.

## Ejemplo de ejecución

Ejecución completa contra MongoDB local (11 de octubre de 2026). Log completo en `logs/log_20261011_2151.txt`
(la importación a MongoDB quedó en `logs/log_20261011_2148.txt`).

```
2026-10-11 21:51:39 | INFO    | etl_airbnb.pipeline | ##### INICIO DEL ETL AIRBNB BOGOTÁ #####
2026-10-11 21:51:39 | INFO    | etl_airbnb.extraccion | Conexión exitosa con MongoDB (mongodb://localhost:27017), base de datos 'airbnb_bogota'
2026-10-11 21:51:39 | INFO    | etl_airbnb.extraccion | Colección 'Calendar': 7,003,255 documentos
2026-10-11 21:51:42 | INFO    | etl_airbnb.extraccion | Extracción de 'Listings': 19,187 registros, 77 columnas (2.4 s)
2026-10-11 21:51:51 | INFO    | etl_airbnb.extraccion | Extracción de 'Reviews': 527,731 registros, 6 columnas (9.6 s)
2026-10-11 21:52:03 | INFO    | etl_airbnb.extraccion | Extracción agregada de 'Calendar' (listing_id x mes): 249,431 registros (11.7 s)
2026-10-11 21:52:03 | INFO    | etl_airbnb.transformacion | Precio normalizado a número (símbolos '$' y ',' eliminados); 195 anuncios sin precio
2026-10-11 21:52:03 | INFO    | etl_airbnb.transformacion | Categorización por rangos ['Económico', 'Bajo', 'Medio', 'Alto', 'Premium']; 659 precios atípicos marcados (> 591,386 COP, Q3+3*IQR), no eliminados
2026-10-11 21:52:05 | INFO    | etl_airbnb.transformacion | amenities desanidado: 505,595 relaciones anuncio-servicio, 3,588 servicios distintos
2026-10-11 21:52:15 | INFO    | etl_airbnb.transformacion | === Fin de la transformación: listings=19,187, hosts=8,335, listing_amenities=505,595, reviews=527,731, calendario_mensual=249,431 ===
2026-10-11 21:52:21 | INFO    | etl_airbnb.carga | Verificación OK: 'reviews' tiene 527,731 filas, igual a lo transformado
2026-10-11 21:55:50 | INFO    | etl_airbnb.pipeline | ##### ETL FINALIZADO CORRECTAMENTE en 251.0 s #####
```

Calendar se resume por anuncio y mes **dentro de MongoDB** (`$group`), por eso el log reporta 249 431 registros extraídos
y no los 7 millones de días; ver la justificación en el notebook.
