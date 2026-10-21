"""Corre una consulta de sql/ y guarda el resultado en DATA_DIR (fuera del repo).

Uso:
    python -m hun.extract sql/00_exploracion/02_llegadas_heatmap.sql
    python -m hun.extract sql/... --nombre llegadas_2023

El resultado queda en DATA_DIR/<nombre>.parquet. Nunca dentro del repo.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config
from .db import engine


def run_sql_file(sql_path: str | Path, nombre: str | None = None) -> Path:
    sql_path = Path(sql_path)
    query = sql_path.read_text(encoding="utf-8")
    out_dir = config.data_dir()  # valida que esté fuera del repo y de la nube
    nombre = nombre or sql_path.stem
    out = out_dir / f"{nombre}.parquet"

    df = pd.read_sql_query(query, engine())
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
