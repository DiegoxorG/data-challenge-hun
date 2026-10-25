"""Lectura de la entrada (CSV o Parquet) y paso al esquema interno:
persona, zona, etiqueta, inicio, fin, caso y atributos."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import Config


def leer(ruta: str | Path, cfg: Config) -> pd.DataFrame:
    ruta = Path(ruta)
    cols = cfg.columnas_entrada
    suf = ruta.suffix.lower()
    if suf == ".sql":
        df = leer_sql(ruta)
    elif suf == ".parquet":
        df = pd.read_parquet(ruta, columns=cols)
    elif suf in (".csv", ".txt"):
        try:
            df = pd.read_csv(ruta, usecols=cols, engine="pyarrow")
        except (ImportError, ValueError):
            df = pd.read_csv(ruta, usecols=cols, low_memory=False)
    else:
        raise ValueError(f"Formato no soportado: {suf} (usa .sql, .csv o .parquet)")
    faltan = [c for c in cols if c not in df.columns]
    if faltan:
        raise ValueError(f"La entrada no tiene las columnas configuradas: {faltan}")
    return df[cols]


def leer_sql(ruta: Path, engine=None) -> pd.DataFrame:
    """Corre un .sql (con `-- @include`) contra la base y deja el resultado SOLO en memoria:
    no escribe ningún archivo por paciente. Usa la conexión del .env (hun.db) salvo que se
    pase otro engine (los tests usan un PostgreSQL local sintético)."""
    from sqlalchemy import text

    from hun.extract import read_sql
    if engine is None:
        from hun.db import engine as crear
        engine = crear()
    with engine.connect() as con:
        return pd.read_sql_query(text(read_sql(ruta)), con)


def _fecha(s: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(s):
        out = s
    else:
        out = pd.to_datetime(s, errors="coerce")
    if getattr(out.dt, "tz", None) is not None:
        out = out.dt.tz_localize(None)
    return out.astype("datetime64[ns]")


def normalizar(crudo: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (df en esquema interno, tabla de nulos y tipos de la entrada)."""
    tipos = []
    for c in cfg.columnas_entrada:
        tipos.append({"columna": c, "tipo_original": str(crudo[c].dtype),
                      "nulos": int(crudo[c].isna().sum()), "p_nulos": float(crudo[c].isna().mean())})
    tipos = pd.DataFrame(tipos)

    df = pd.DataFrame({
        "persona": _codigo(crudo[cfg.persona]),
        "zona": _codigo(crudo[cfg.zona]),
        "inicio": _fecha(crudo[cfg.inicio]),
        "fin": _fecha(crudo[cfg.fin]),
    })
    # Fechas que no se pudieron interpretar (distintas de las que ya venían nulas)
    no_parse = {cfg.inicio: int((df["inicio"].isna() & crudo[cfg.inicio].notna()).sum()),
                cfg.fin: int((df["fin"].isna() & crudo[cfg.fin].notna()).sum())}
    tipos["no_interpretables"] = tipos["columna"].map(no_parse).fillna(0).astype(int)

    df["etiqueta"] = crudo[cfg.etiqueta_zona].astype("string") if cfg.etiqueta_zona else df["zona"]
    if cfg.caso:
        df["caso"] = crudo[cfg.caso].astype("string")

    for a in cfg.atributos:
        if a.columna == "edad" and cfg.edad_desde_anio_nacimiento:
            continue
        df[f"attr_{a.columna}"] = crudo[a.columna]
    if cfg.edad_desde_anio_nacimiento:
        # Edad al momento del segmento: año del inicio menos año de nacimiento (sin fecha fija)
        nac = pd.to_numeric(crudo[cfg.edad_desde_anio_nacimiento], errors="coerce")
        df["attr_edad"] = df["inicio"].dt.year - nac

    if cfg.desde:
        df = df[df["inicio"] >= pd.Timestamp(cfg.desde)]
    if cfg.hasta:
        df = df[df["inicio"] < pd.Timestamp(cfg.hasta)]
    # Filtros por código de la entrada, antes de agrupar
    if cfg.zonas_incluir:
        df = df[df["zona"].isin(cfg.zonas_incluir)]
    if cfg.zonas_excluir:
        df = df[~df["zona"].isin(cfg.zonas_excluir)]
    if cfg.zonas_agrupar:
        df = agrupar_zonas(df, cfg)
    return df.reset_index(drop=True), tipos


def agrupar_zonas(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Reemplaza los códigos agrupados por el nombre del grupo (y su etiqueta). Guarda el código
    original en `zona_original`. Las zonas fuera de todo grupo quedan como estaban."""
    mapa = {c: g for g, gr in cfg.zonas_agrupar.items() for c in gr.codigos}
    etq = {g: gr.etiqueta for g, gr in cfg.zonas_agrupar.items()}
    df = df.copy()
    df["zona_original"] = df["zona"]
    nueva = df["zona"].map(mapa)
    agrupada = nueva.notna()
    df["zona"] = nueva.where(agrupada, df["zona"]).astype("string")
    df["etiqueta"] = df["zona"].map(etq).where(agrupada, df["etiqueta"]).astype("string")
    return df


def _codigo(s: pd.Series) -> pd.Series:
    """Identificadores como texto. Si la columna es numérica con valores enteros (p. ej. un
    concept_id que llegó como float por tener nulos), evita el '.0' para que '9203' coincida
    con lo que se escribe en el config."""
    if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
        x = pd.to_numeric(s, errors="coerce")
        if bool(((x.dropna() % 1) == 0).all()):
            return x.astype("Int64").astype("string")
    return s.astype("string")


def etiquetas_zona(df: pd.DataFrame) -> dict[str, str]:
    """Nombre para mostrar por zona: la etiqueta más frecuente; si dos zonas comparten
    etiqueta, se agrega el código para distinguirlas."""
    if df.empty:
        return {}
    et = (df.groupby(["zona", "etiqueta"], observed=True).size().reset_index(name="n")
          .sort_values("n", ascending=False).drop_duplicates("zona").set_index("zona")["etiqueta"])
    et = et.fillna(pd.Series(et.index, index=et.index)).astype(str)
    rep = et.duplicated(keep=False)
    return {z: (f"{e} [{z}]" if rep[z] or e == "" else e) for z, e in et.items()}
