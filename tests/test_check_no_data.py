"""El guardián anti-fuga bloquea lo que debe y deja pasar el código normal (todo inventado)."""
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "check_no_data", Path(__file__).resolve().parents[1] / "scripts" / "check_no_data.py")
cnd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cnd)


def nb(celdas):
    return json.dumps({"cells": celdas, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}).encode()


def code(src, outputs=None):
    return {"cell_type": "code", "source": src, "outputs": outputs or [], "metadata": {}, "execution_count": None}


@pytest.mark.parametrize("ruta", ["extracto.csv", "a/b/datos.parquet", "dashboard/tablero.pbix", "data/x.txt", ".env"])
def test_bloquea_archivos_de_datos(ruta):
    assert cnd.check(ruta, b"x")


def test_codigo_limpio_pasa():
    assert cnd.check("src/x.py", b"import pandas as pd\nprint('hola')\n") == []
    assert cnd.check(".env.example", b"PGPASSWORD=\nPGUSER=tu_usuario_hun\n") == []


def test_contrasena_en_script_de_powershell():
    # Se arma por partes para que este archivo no lleve una contraseña "literal" (si no, el hook lo bloquea)
    linea = ("$env:PG" + "PASSWORD=" + "Inventada123\n").encode()
    assert any("PGPASSWORD" in p for p in cnd.check("paso5.ps1", linea))


def test_notebook_con_outputs_o_imagenes():
    sucio = nb([code("1+1", outputs=[{"output_type": "stream", "name": "stdout", "text": "2"}])])
    assert any("outputs" in p for p in cnd.check("n.ipynb", sucio))
    img = nb([{"cell_type": "markdown", "source": "![a](attachment:a.png)", "metadata": {},
               "attachments": {"a.png": {"image/png": "iVBOR"}}}])
    assert any("imágenes" in p for p in cnd.check("n.ipynb", img))


def test_tabla_pegada_dentro_de_un_notebook():
    filas = "\n".join(f"{i},2024-01-0{i % 9 + 1},9203,{i * 3},alta" for i in range(60))
    assert any("forma de tabla" in p for p in cnd.check("n.ipynb", nb([code(filas)])))
    assert cnd.check("n.ipynb", nb([code("x = 1")])) == []


def test_reporte_generado_con_la_marca():
    marca = '<meta name="hun-' + 'datos" content="derivado">'
    assert any("hun-datos" in p for p in cnd.check("algo.html", f"<html><head>{marca}</head></html>".encode()))
