"""Corre una consulta de sql/ y guarda el resultado en DATA_DIR (fuera del repo).

Uso:
    python -m hun.extract sql/00_exploracion/02_llegadas_heatmap.sql
    python -m hun.extract sql/... --nombre llegadas_2023

El resultado queda en DATA_DIR/<nombre>.parquet. Nunca dentro del repo.
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from . import config
from .db import engine


_INCLUDE = re.compile(r"^[ \t]*--[ \t]*@include[ \t]+(\S+)[ \t]*$", re.M)


def read_sql(sql_path: str | Path, _pila: tuple[Path, ...] = ()) -> str:
    """Lee un .sql y reemplaza las líneas `-- @include archivo.sql` por el contenido
    de ese archivo. Sirve para reutilizar bloques comunes, como la construcción de
    episodios. Solo se aceptan archivos .sql de la MISMA carpeta (sin rutas) y se
    detectan inclusiones circulares."""
    sql_path = Path(sql_path).resolve()
    if sql_path in _pila:
        raise ValueError(f"@include circular: {' -> '.join(p.name for p in (*_pila, sql_path))}")
    texto = sql_path.read_text(encoding="utf-8")

    def _incluir(m: re.Match) -> str:
        nombre = m.group(1)
        if Path(nombre).name != nombre or not nombre.endswith(".sql"):
            raise ValueError(f"@include solo acepta un .sql de la misma carpeta, sin rutas: {nombre!r}")
        return read_sql(sql_path.parent / nombre, (*_pila, sql_path)).rstrip()

    return _INCLUDE.sub(_incluir, texto)


def run_sql_file(sql_path: str | Path, nombre: str | None = None) -> Path:
    sql_path = Path(sql_path)
    query = read_sql(sql_path)
    out_dir = config.data_dir()  # valida que esté fuera del repo y de la nube
    nombre = nombre or sql_path.stem
    out = out_dir / f"{nombre}.parquet"

    df = pd.read_sql_query(text(query), engine())
    df.to_parquet(out, index=False)

    # Solo metadatos en consola: forma y columnas, nunca filas
    print(f"[{datetime.now():%H:%M}] {sql_path.name} -> {out}")
    print(f"  filas={len(df):,}  columnas={list(df.columns)}")
    return out


def load(nombre: str) -> pd.DataFrame:
    """Carga un extracto guardado en DATA_DIR."""
    return pd.read_parquet(config.data_dir() / f"{nombre}.parquet")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sql")
    ap.add_argument("--nombre")
    a = ap.parse_args()
    run_sql_file(a.sql, a.nombre)
