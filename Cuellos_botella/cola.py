"""I. Cola larga: qué parte de las horas-paciente de cada zona aportan las estancias más largas."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import figuras as F
from .comun import Contexto, Registro

SEC = "I. Cola larga"
CORTES = [0.01, 0.05, 0.10, 0.20]


def curva_pareto(minutos: np.ndarray, n: int = 201) -> tuple[np.ndarray, np.ndarray]:
    """(fracción de estancias más largas, fracción de horas-paciente que aportan), en una rejilla."""
    m = np.sort(np.asarray(minutos, dtype=float))[::-1]
    m = m[~np.isnan(m)]
    if m.size == 0 or m.sum() <= 0:
        return np.array([]), np.array([])
    acum = np.concatenate([[0.0], np.cumsum(m) / m.sum()])
    x = np.linspace(0, 1, n)
    return x, np.interp(x * m.size, np.arange(m.size + 1), acum)


def correr(ctx: Contexto, reg: Registro) -> None:
    filas, fig = [], go.Figure()
    grupos = [(z, ctx.est.loc[ctx.est["zona"] == z, "min"].to_numpy()) for z in ctx.zonas]
    grupos.append(("__episodios__", ctx.epi["min"].to_numpy()))
    for z, m in grupos:
        x, y = curva_pareto(m)
        if x.size == 0:
            continue
        nombre = "episodios completos" if z == "__episodios__" else ctx.nombre(z)
        col = F.TINTA if z == "__episodios__" else F.color_zona(ctx.zonas, z)
        fig.add_scatter(x=x, y=y, mode="lines", name=nombre,
                        line=dict(color=col, width=2, dash="dash" if z == "__episodios__" else "solid"),
                        hovertemplate="el %{x:.0%} más largo aporta el %{y:.0%} de las horas<extra>" + nombre + "</extra>")
        filas.append({"zona": z, "nombre": nombre,
                      **{f"p_horas_top_{int(c * 100)}pct": float(np.interp(c, x, y)) for c in CORTES}})
    fig.add_scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(color=F.MUTED, width=1, dash="dot"),
                    name="todas iguales", hoverinfo="skip")
    fig.update_xaxes(tickformat=".0%")
    fig.update_yaxes(tickformat=".0%")
    reg.tabla(SEC, "pareto_zona", pd.DataFrame(filas),
              "Por zona (y para episodios completos): fracción de las horas-paciente que aportan el 1 %, 5 %, 10 % y "
              "20 % de las estancias más largas.")
    reg.fig(SEC, "Curva de Pareto de horas-paciente", F.estilo(fig, "fracción de estancias, de la más larga a la más corta",
                                                              "fracción acumulada de horas-paciente", alto=460),
            "Ordenando las estancias de cada zona de la más larga a la más corta, la curva muestra qué fracción del "
            "total de horas-paciente acumulan. La diagonal punteada sería el caso en que todas duran lo mismo; "
            "cuanto más se separa la curva hacia arriba, más concentradas están las horas en pocas estancias largas.")
