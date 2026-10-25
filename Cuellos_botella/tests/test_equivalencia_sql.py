"""La herramienta (Python) y las consultas oficiales (SQL) dan lo mismo sobre la base SINTÉTICA.

Compara, con el config.yaml del repo y sql/02_cuellos_botella/entrada.sql:
  1. episodios     vs sql/01_episodios/_episodios.sql (ep)
  2. tiempos       vs epu (destino, min_urg, min_hosp), base de la consulta 20 (sin recorte)
  3. ocupación     vs la consulta 25 (con recorte y sin estancias largas)

Los episodios son idénticos. En tiempos y ocupación hay UNA diferencia de definición, que
el test acota: episodios "irregulares", donde una zona aparece más de una vez o urgencias
aparece después de la hospitalización (p. ej. urgencias → hospitalización → urgencias).
  - El SQL mide min_urg = último fin de urgencias − llegada, así que incluye el tiempo en cama.
    La herramienta suma las estancias de urgencias por separado.
  - La 25 cuenta un solo tramo de urgencias por episodio (llegada → ingreso a cama) y solo en
    episodios que empiezan en urgencias; la herramienta cuenta cada estancia.
Fuera de esos episodios, todo debe coincidir exacto. Cuántos irregulares hay en la base real
lo dice el resumen seguro ("episodios irregulares").

Necesita un PostgreSQL LOCAL con el esquema de scripts/generar_sintetico.py:
  $env:HUN_TEST_PG_URL = "postgresql://yo@localhost:5432/omop_sintetico"     # PowerShell
  python -m pytest Cuellos_botella/tests/test_equivalencia_sql.py
Sin HUN_TEST_PG_URL se salta. Se niega a correr contra un host no local o un esquema sin
la marca _es_sintetico, así que no puede tocar la base del HUN.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from Cuellos_botella import calidad, carga, episodios
from Cuellos_botella.comun import Contexto, Registro
from Cuellos_botella.config import cargar

REPO = Path(__file__).resolve().parents[2]
URL = os.getenv("HUN_TEST_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="sin HUN_TEST_PG_URL (PostgreSQL local sintético)")


def _generador():
    spec = importlib.util.spec_from_file_location("generar_sintetico", REPO / "scripts" / "generar_sintetico.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def eng():
    from sqlalchemy import create_engine
    gen = _generador()
    gen._validar_url(URL)                               # host local explícito, sin trucos en la URL
    url = "postgresql+psycopg2://" + URL.split("://", 1)[1]
    e = create_engine(url, connect_args={"options": "-csearch_path=uninorte_omop"})
    with e.connect() as c:
        cur = c.connection.cursor()
        gen._verificar_servidor_local(cur)
        cur.execute("SELECT to_regclass('uninorte_omop._es_sintetico') IS NOT NULL")
        if not cur.fetchone()[0]:
            pytest.fail("el esquema uninorte_omop no tiene la marca _es_sintetico: no es la base sintética")
    return e


def _sql(eng, archivo: Path, final: str = "") -> pd.DataFrame:
    from sqlalchemy import text

    from hun.extract import read_sql
    with eng.connect() as c:
        return pd.read_sql_query(text(read_sql(archivo) + final), c)


def _python(eng, tmp: Path, **cambios):
    """Corre carga → calidad → episodios con el config del repo (y los cambios pedidos)."""
    cfg = dataclasses.replace(cargar(REPO / "Cuellos_botella" / "config.yaml"), **cambios)
    crudo = carga.leer_sql(REPO / "sql" / "02_cuellos_botella" / "entrada.sql", engine=eng)
    df, tipos = carga.normalizar(crudo[cfg.columnas_entrada], cfg)
    reg = Registro(tmp)
    etq = carga.etiquetas_zona(df)
    validos, meses = calidad.analizar(df, tipos, cfg, reg, etq)
    ctx = Contexto(cfg=cfg, seg=validos, etiquetas=etq, zonas=list(validos["zona"].value_counts().index),
                   meses_incompletos=meses)
    episodios.correr(ctx, reg)
    return ctx


def _irregulares(epi: pd.DataFrame) -> set:
    """Episodios que no son 'una zona' ni 'urgencias → hospitalización'."""
    regular = (epi["n_estancias"] == 1) | ((epi["n_estancias"] == 2) & (epi["zona_inicial"] == "urgencias")
                                           & (epi["zona_final"] == "hospitalizacion"))
    return set(epi.loc[~regular, "episodio"])


def test_episodios_iguales(eng, tmp_path):
    sql = _sql(eng, REPO / "sql" / "01_episodios" / "_episodios.sql", "\nSELECT person_id, ini, fin FROM ep")
    py = _python(eng, tmp_path).epi
    a = set(zip(sql["person_id"].astype(str), sql["ini"], sql["fin"]))
    b = set(zip(py["persona"], py["inicio"], py["fin"]))
    assert len(a) > 100, "la base sintética está casi vacía"
    assert a == b, f"solo en SQL: {len(a - b)}, solo en Python: {len(b - a)}"


def test_tiempos_por_destino_iguales(eng, tmp_path):
    sql = _sql(eng, REPO / "sql" / "01_episodios" / "_episodios.sql",
               "\nSELECT person_id, llegada, destino, min_urg, min_hosp FROM epu")
    ctx = _python(eng, tmp_path, recortar_al_siguiente=False, excluir_estancias_largas={})
    est, epi = ctx.est, ctx.epi
    urg = est[est["zona"] == "urgencias"].groupby("episodio").agg(llegada=("inicio", "min"), min_urg=("min", "sum"))
    hosp = est[est["zona"] == "hospitalizacion"].groupby("episodio")["min"].sum().rename("min_hosp")
    e = epi[epi["zona_inicial"] == "urgencias"].set_index("episodio").join(urg).join(hosp)
    e["destino"] = np.where(e["min_hosp"].notna(), "hospitalizado", "alta")
    e["irregular"] = e.index.isin(_irregulares(epi))

    m = sql.assign(persona=sql["person_id"].astype(str)).merge(
        e.reset_index(), on=["persona", "llegada"], how="outer", suffixes=("_sql", "_py"), indicator=True)
    assert (m["_merge"] == "both").all(), "hay episodios de urgencias que solo están en un lado"
    igual = ((m["destino_sql"] == m["destino_py"])
             & np.isclose(m["min_urg_sql"].astype(float), m["min_urg_py"], atol=1e-6)
             & (np.isclose(m["min_hosp_sql"].astype(float), m["min_hosp_py"], atol=1e-6)
                | (m["min_hosp_sql"].isna() & m["min_hosp_py"].isna())))
    assert igual[~m["irregular"]].all(), f"{int((~igual & ~m['irregular']).sum())} episodios regulares no coinciden"
    assert m["irregular"].mean() < 0.01, "demasiados episodios irregulares en la base sintética"


def test_ocupacion_igual_a_la_25(eng, tmp_path):
    sql = _sql(eng, REPO / "sql" / "01_episodios" / "25_ocupacion_ajustada.sql")
    ctx = _python(eng, tmp_path)
    est, irr = ctx.est, _irregulares(ctx.epi)
    h = pd.DatetimeIndex(sql["hora"]).to_numpy()

    def censo(e):
        # Misma convención que la 25: en la hora h están los que entraron en una hora <= h y
        # no salieron en una hora <= h (eventos truncados a la hora).
        ent = np.sort(e["inicio"].dt.floor("h").to_numpy())
        sal = np.sort(e["fin"].dt.floor("h").to_numpy())
        return np.searchsorted(ent, h, "right") - np.searchsorted(sal, h, "right")

    # Horas en las que algún episodio irregular está en curso (de su primer inicio a su último fin)
    epi_irr = ctx.epi[ctx.epi["episodio"].isin(irr)]
    toca_irr = censo(epi_irr) > 0
    for zona, col in [("urgencias", "en_urgencias"), ("hospitalizacion", "en_hospitalizacion")]:
        dif = censo(est[est["zona"] == zona]) != sql[col].to_numpy()
        assert not (dif & ~toca_irr).any(), f"{zona}: {int((dif & ~toca_irr).sum())} horas distintas sin irregulares"
