"""Piezas compartidas: conversión de tiempos, percentiles, contexto del análisis
y el registro de figuras/tablas que alimenta el reporte."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config

PCTS = [10, 25, 50, 75, 90, 95, 99]
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
FIN = "(fin del episodio)"


def segundos(s: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    """Fechas -> segundos epoch en float (NaT -> NaN). Float64 alcanza: precisión sub-segundo."""
    arr = np.asarray(s, dtype="datetime64[ns]")
    out = arr.astype("int64").astype("float64") / 1e9
    out[np.isnat(arr)] = np.nan
    return out


def tabla_percentiles(df: pd.DataFrame, por: str | list[str], col: str, pcts=PCTS) -> pd.DataFrame:
    """n, media y percentiles de `col` por grupo, en una tabla ancha."""
    g = df.groupby(por, observed=True)[col]
    q = g.quantile([p / 100 for p in pcts]).unstack()
    q.columns = [f"p{p}" for p in pcts]
    out = pd.concat([g.size().rename("n"), g.mean().rename("media"), q], axis=1)
    return out.reset_index()


def cuantiles_rejilla(x: np.ndarray, n: int = 201) -> tuple[np.ndarray, np.ndarray]:
    """ECDF resumida en una rejilla de cuantiles (no embebe datos individuales)."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if x.size == 0:
        return np.array([]), np.array([])
    q = np.linspace(0, 1, n)
    return np.quantile(x, q), q


@dataclass
class Contexto:
    cfg: Config
    seg: pd.DataFrame                 # segmentos válidos (persona, zona, inicio, fin, ...)
    etiquetas: dict[str, str]         # zona -> nombre para mostrar
    zonas: list[str]                  # zonas ordenadas por frecuencia (orden fijo de colores)
    meses_incompletos: set = field(default_factory=set)   # pd.Period mensuales
    est: pd.DataFrame | None = None   # estancias (segmentos seguidos de la misma zona unidos)
    epi: pd.DataFrame | None = None   # episodios
    censo: pd.DataFrame | None = None # censo horario largo (hora, zona, censo_inst, censo_medio)

    def nombre(self, z) -> str:
        return self.etiquetas.get(z, str(z))

    def completo(self, fechas: pd.Series) -> pd.Series:
        """True si la fecha cae en un mes no marcado como incompleto."""
        if not self.meses_incompletos:
            return pd.Series(True, index=fechas.index)
        return ~fechas.dt.to_period("M").isin(self.meses_incompletos)

    def dias_por_dow(self, inicio: pd.Timestamp, fin: pd.Timestamp) -> pd.Series:
        """Cuántos días de cada día de la semana hay en meses completos del rango."""
        dias = pd.Series(pd.date_range(inicio.normalize(), fin.normalize(), freq="D"))
        dias = dias[self.completo(dias)]
        return dias.dt.dayofweek.value_counts().reindex(range(7), fill_value=0)


@dataclass
class Figura:
    seccion: str
    titulo: str
    fig: object
    leyenda: str


class Registro:
    """Acumula figuras, tablas y avisos; las tablas se escriben a CSV de inmediato."""

    def __init__(self, salida: Path):
        self.salida = Path(salida)
        (self.salida / "tablas").mkdir(parents=True, exist_ok=True)
        self.figuras: list[Figura] = []
        self.tablas: list[tuple[str, str, str]] = []   # (seccion, nombre, descripcion)
        self.avisos: list[str] = []
        self.errores: list[str] = []

    def fig(self, seccion: str, titulo: str, fig, leyenda: str) -> None:
        self.figuras.append(Figura(seccion, titulo, fig, leyenda))

    def tabla(self, seccion: str, nombre: str, df: pd.DataFrame, descripcion: str) -> None:
        df.to_csv(self.salida / "tablas" / f"{nombre}.csv", index=False, encoding="utf-8")
        self.tablas.append((seccion, nombre, descripcion))

    def aviso(self, texto: str) -> None:
        self.avisos.append(texto)
