"""Configuración común de pytest para todo el repo.

- Permite `import hun`, `import Cuellos_botella` e `import series_tiempo` desde cualquier carpeta,
  aunque no se haya hecho `pip install -e .`.
- Fixture `eng`: conexión a la base SINTÉTICA local (HUN_TEST_PG_URL). Se salta si no está
  definida y se niega a seguir si el host no es local o el esquema no tiene la marca
  _es_sintetico, así que ningún test puede tocar la base del HUN.
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent
for _p in (RAIZ, RAIZ / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

URL_SINTETICA = os.getenv("HUN_TEST_PG_URL")


def _generador():
    spec = importlib.util.spec_from_file_location("generar_sintetico", RAIZ / "scripts" / "generar_sintetico.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def eng():
    if not URL_SINTETICA:
        pytest.skip("sin HUN_TEST_PG_URL (PostgreSQL local sintético)")
    from sqlalchemy import create_engine
    gen = _generador()
    gen._validar_url(URL_SINTETICA)                       # host local explícito, sin trucos en la URL
    e = create_engine("postgresql+psycopg2://" + URL_SINTETICA.split("://", 1)[1],
                      connect_args={"options": "-csearch_path=uninorte_omop"})
    with e.connect() as c:
        cur = c.connection.cursor()
        gen._verificar_servidor_local(cur)
        cur.execute("SELECT to_regclass('uninorte_omop._es_sintetico') IS NOT NULL")
        if not cur.fetchone()[0]:
            pytest.fail("el esquema uninorte_omop no tiene la marca _es_sintetico: no es la base sintética")
    return e
