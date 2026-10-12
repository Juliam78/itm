import sqlite3

from src.pipeline import ejecutar_pipeline


def test_pipeline_de_punta_a_punta_con_mongomock(cliente_mongo, tmp_path):
    resultado = ejecutar_pipeline(
        cliente_mongo=cliente_mongo, base_datos="airbnb_test",
        ruta_sqlite=tmp_path / "e2e.db", dir_xlsx=tmp_path / "x",
    )
    assert resultado["carga"]["verificacion"]["ok"].all()
    assert len(resultado["carga"]["xlsx"]) == 4
    with sqlite3.connect(tmp_path / "e2e.db") as con:
        tablas = {f[0] for f in con.execute("SELECT name FROM sqlite_master WHERE type=\'table\'")}
    assert {"listings", "hosts", "reviews", "listing_amenities", "calendario_mensual"} <= tablas
    texto = resultado["log"].read_text(encoding="utf-8")
    assert "INICIO DEL ETL" in texto and "ETL FINALIZADO CORRECTAMENTE" in texto
    assert resultado["log"].name.startswith("log_") and resultado["log"].suffix == ".txt"


def test_pipeline_registra_error_y_relanza_si_mongo_no_tiene_datos(tmp_path):
    import mongomock
    import pytest
    from src.extraccion import ErrorExtraccion

    with pytest.raises(ErrorExtraccion):
        ejecutar_pipeline(cliente_mongo=mongomock.MongoClient(), base_datos="vacia",
                          ruta_sqlite=tmp_path / "x.db", dir_xlsx=tmp_path / "x")
