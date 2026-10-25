"""Series agregadas para el pronóstico: se leen de la base con las consultas 26-28 (o de una
corrida anterior), se completan con calendario y marcas de meses incompletos, y se guardan en
DATA_DIR. Todo es agregado por hora, día o semana: ninguna fila es un paciente.

Para modelar:
    from series_tiempo import cargar
    s = cargar()            # dict con 'horas', 'dias', 'grupos', 'semanas'
    y = s["dias"].loc[s["dias"]["completo"], "llegadas"]
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import calendario

REPO_ROOT = Path(__file__).resolve().parents[1]
SQL = REPO_ROOT / "sql" / "01_episodios"
CONSULTAS = {"horas": "26_series_horarias.sql", "grupos": "27_llegadas_diarias_por_grupo.sql",
             "semanas": "28_tiempos_semanales.sql"}
CARPETA_DEFECTO = "series_tiempo"
CONTEOS = ["llegadas", "llegadas_hospitalizan", "llegadas_contacto_breve", "ingresos_cama",
           "ingresos_desde_urgencias", "altas_cama"]
CENSOS = ["censo_urgencias", "censo_hospitalizacion"]


@dataclass
class Series:
    horas: pd.DataFrame                 # índice hora; conteos por hora y censos (foto de cada hora)
    dias: pd.DataFrame                  # índice fecha; conteos por día, censo medio y calendario
    grupos: pd.DataFrame                # índice fecha; columnas (dimension, grupo) con llegadas
    semanas: pd.DataFrame               # semana, destino, percentiles de tiempos (grupos >= 10)
    meses_incompletos: set              # pd.Period mensuales


# --- dónde se guarda ---------------------------------------------------------------
def carpeta_salida(ruta: str | Path | None) -> Path:
    """Por defecto DATA_DIR/series_tiempo. Nunca dentro del repo ni en una carpeta en la nube."""
    from hun.config import validar_carpeta
    if ruta is None:
        try:
            from hun.config import data_dir
        except Exception as e:  # pragma: no cover - depende del entorno
            raise RuntimeError("No pude obtener DATA_DIR (¿pip install -e . y .env lleno?). Usa --salida.") from e
        d = data_dir() / CARPETA_DEFECTO
    else:
        d = Path(ruta)
    d = validar_carpeta(d, "La salida")
    (d / "datos").mkdir(parents=True, exist_ok=True)
    return d


# --- lectura -------------------------------------------------------------------------
def leer_base(engine=None) -> dict[str, pd.DataFrame]:
    """Corre las consultas 26-28 (agregadas) y devuelve los resultados en memoria."""
    from sqlalchemy import text

    from hun.extract import es_nivel_paciente, read_sql
    if engine is None:
        from hun.db import engine as crear
        engine = crear()
    crudo = {}
    with engine.connect() as con:
        for nombre, archivo in CONSULTAS.items():
            q = read_sql(SQL / archivo)
            if es_nivel_paciente(q):           # defensa: estas consultas deben ser agregadas
                raise RuntimeError(f"{archivo} está marcado como nivel paciente; no se usa aquí")
            crudo[nombre] = pd.read_sql_query(text(q), con)
    return crudo


def leer_guardado(salida: Path) -> dict[str, pd.DataFrame]:
    d = Path(salida) / "datos"
    faltan = [n for n in ("horas_crudo", "grupos_crudo", "semanas_crudo") if not (d / f"{n}.parquet").exists()]
    if faltan:
        raise FileNotFoundError(f"No encontré {faltan} en {d}. Corre primero sin --sin-base.")
    return {k: pd.read_parquet(d / f"{k}_crudo.parquet") for k in ("horas", "grupos", "semanas")}


def guardar_crudo(crudo: dict[str, pd.DataFrame], salida: Path) -> None:
    for k, df in crudo.items():
        df.to_parquet(Path(salida) / "datos" / f"{k}_crudo.parquet", index=False)


# --- armado ----------------------------------------------------------------------------
def meses_incompletos(dias: pd.Series, frac: float = 0.5, cobertura: float = 0.9) -> set:
    """Mismo criterio que Cuellos_botella: un mes con menos llegadas por día que `frac` × la
    mediana, o el primero/último si el rango cubre menos de `cobertura` del mes."""
    if dias.empty:
        return set()
    mes = dias.index.to_period("M")
    por_dia = dias.groupby(mes).mean()
    cubiertos = dias.groupby(mes).size()
    largo = pd.Series([p.days_in_month for p in por_dia.index], index=por_dia.index)
    malos = set(por_dia.index[por_dia < frac * por_dia.median()])
    for p in (por_dia.index[0], por_dia.index[-1]):
        if cubiertos[p] < cobertura * largo[p]:
            malos.add(p)
    return malos


def armar(crudo: dict[str, pd.DataFrame]) -> Series:
    h = crudo["horas"].copy()
    h["hora"] = pd.to_datetime(h["hora"])
    h = h.set_index("hora").sort_index().asfreq("h")
    h[CONTEOS] = h[CONTEOS].fillna(0).astype(int)
    h[CENSOS] = h[CENSOS].ffill().fillna(0)

    d = h[CONTEOS].resample("D").sum()
    d[[f"{c}_medio" for c in CENSOS]] = h[CENSOS].resample("D").mean().to_numpy()
    d[[f"{c}_max" for c in CENSOS]] = h[CENSOS].resample("D").max().to_numpy()
    d.index.name = "fecha"
    meses = meses_incompletos(d["llegadas"])
    d = d.join(calendario.tabla(d.index.min(), d.index.max())) if len(d) else d
    # Días cortados por el extracto (el primero y el último casi nunca tienen las 24 horas)
    horas_por_dia = h["llegadas"].resample("D").size()
    d["completo"] = ~d.index.to_period("M").isin(meses) & (horas_por_dia.reindex(d.index) == 24).to_numpy()
    h["completo"] = d["completo"].reindex(h.index.normalize()).to_numpy()

    g = crudo["grupos"].copy()
    if len(g):
        g["fecha"] = pd.to_datetime(g["fecha"])
        g = (g.pivot_table(index="fecha", columns=["dimension", "grupo"], values="llegadas", aggfunc="sum")
             .reindex(d.index).fillna(0).astype(int))
    else:
        g = pd.DataFrame(index=d.index)

    s = crudo["semanas"].copy()
    if len(s):
        s["semana"] = pd.to_datetime(s["semana"])
        s["completo"] = ~s["semana"].dt.to_period("M").isin(meses)
    return Series(horas=h, dias=d, grupos=g, semanas=s, meses_incompletos=meses)


def guardar_series(s: Series, salida: Path) -> list[Path]:
    """Lo que Sebastián usa para modelar: series limpias con calendario, en DATA_DIR."""
    d = Path(salida) / "datos"
    out = []
    for nombre, df in (("series_horarias", s.horas.reset_index()), ("series_diarias", s.dias.reset_index()),
                       ("semanas_tiempos", s.semanas)):
        p = d / f"{nombre}.parquet"
        df.to_parquet(p, index=False)
        out.append(p)
    g = s.grupos.copy()
    g.columns = [f"{a}__{b}" for a, b in g.columns] if isinstance(g.columns, pd.MultiIndex) else g.columns
    p = d / "llegadas_diarias_por_grupo.parquet"
    g.reset_index().to_parquet(p, index=False)
    out.append(p)
    return out


def cargar(salida: str | Path | None = None) -> dict[str, pd.DataFrame]:
    """Carga las series guardadas por `python -m series_tiempo` para modelar.
    'horas' y 'dias' traen la columna `completo` (False = mes incompleto: no usar para entrenar)."""
    d = carpeta_salida(salida) / "datos"
    h = pd.read_parquet(d / "series_horarias.parquet").set_index("hora").asfreq("h")
    dd = pd.read_parquet(d / "series_diarias.parquet").set_index("fecha").asfreq("D")
    g = pd.read_parquet(d / "llegadas_diarias_por_grupo.parquet").set_index("fecha")
    g.columns = pd.MultiIndex.from_tuples([tuple(c.split("__", 1)) for c in g.columns], names=["dimension", "grupo"])
    return {"horas": h, "dias": dd, "grupos": g, "semanas": pd.read_parquet(d / "semanas_tiempos.parquet")}


def tramo_continuo(mascara: pd.Series) -> pd.Series:
    """El tramo más largo de True seguidos (para STL, ACF y pruebas, que piden serie sin huecos)."""
    m = mascara.to_numpy(dtype=bool)
    if not m.any():
        return mascara & False
    grupos = np.cumsum(~m)
    largo = pd.Series(m.astype(int)).groupby(grupos).transform("sum").to_numpy() * m
    mejor = grupos[np.argmax(largo)]
    return pd.Series((grupos == mejor) & m, index=mascara.index)
