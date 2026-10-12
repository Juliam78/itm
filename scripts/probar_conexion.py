"""Comprueba la conexión con MongoDB y el estado de las colecciones del taller.

Uso (desde la raíz del proyecto)::

    python scripts/probar_conexion.py

Equivale al ``scripts/probar_conexiones.py`` del repositorio de ejemplo, pero
limitado a MongoDB y con la validación de las tres colecciones requeridas.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.extraccion import Extraccion, ErrorExtraccion


def main() -> int:
    try:
        with Extraccion() as extraccion:
            conteos = extraccion.validar_colecciones()
    except ErrorExtraccion as error:
        print(f"ERROR: {error}")
        return 1
    print("MongoDB: conexión correcta y colecciones disponibles")
    for clave, total in conteos.items():
        print(f"  {extraccion.colecciones[clave]}: {total:,} documentos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
