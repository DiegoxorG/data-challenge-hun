"""Las consultas 26-28 cuadran con la 21 y la 25 sobre la base SINTÉTICA local.
Se salta sin HUN_TEST_PG_URL; se niega a correr contra un host no local o un esquema sin la
marca _es_sintetico (mismas defensas que el test de equivalencia de Cuellos_botella)."""
import os
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
URL = os.getenv("HUN_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="sin HUN_TEST_PG_URL (PostgreSQL local sintético)")


def test_26_cuadra_con_21_y_25(eng):
    from sqlalchemy import text

    from hun.extract import read_sql
    from series_tiempo import datos

    crudo = datos.leer_base(eng)
    h = crudo["horas"]
    with eng.connect() as c:
        s21 = pd.read_sql_query(text(read_sql(REPO / "sql/01_episodios/21_llegadas_por_hora.sql")), c)
        s25 = pd.read_sql_query(text(read_sql(REPO / "sql/01_episodios/25_ocupacion_ajustada.sql")), c)
    assert (pd.to_datetime(h["hora"]).diff().dropna() == pd.Timedelta("1h")).all()     # rejilla completa
    m = s21.merge(h, on="hora", suffixes=("_21", ""))
    assert len(m) == len(s21) and (m["llegadas_21"] == m["llegadas"]).all()
    assert h["llegadas"].sum() == s21["llegadas"].sum()
    m = s25.merge(h, on="hora")
    assert (m["en_urgencias"] == m["censo_urgencias"]).all()
    assert (m["en_hospitalizacion"] == m["censo_hospitalizacion"]).all()
    assert crudo["semanas"]["episodios"].min() >= 10                                    # grupos pequeños fuera
    assert set(crudo["grupos"]["dimension"]) == {"sexo", "edad", "destino"}
