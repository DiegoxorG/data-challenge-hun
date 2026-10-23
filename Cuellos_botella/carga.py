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
    if suf == ".parquet":
        df = pd.read_parquet(ruta, columns=cols)
    elif suf in (".csv", ".txt"):
        try:
            df = pd.read_csv(ruta, usecols=cols, engine="pyarrow")
        except (ImportError, ValueError):
            df = pd.read_csv(ruta, usecols=cols, low_memory=False)
    else:
        raise ValueError(f"Formato no soportado: {suf} (usa .csv o .parquet)")
    faltan = [c for c in cols if c not in df.columns]
    if faltan:
        raise ValueError(f"La entrada no tiene las columnas configuradas: {faltan}")
    return df


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
        "persona": crudo[cfg.persona].astype("string"),
        "zona": crudo[cfg.zona].astype("string"),
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
    if cfg.zonas_excluir:
        df = df[~df["zona"].isin(cfg.zonas_excluir)]
    return df.reset_index(drop=True), tipos


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
