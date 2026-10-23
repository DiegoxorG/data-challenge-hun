"""Ayudas de Plotly: paleta fija, estilo base, selector de zona y transformaciones.
Todas las figuras se arman con datos ya agregados (cuantiles, conteos), nunca filas."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

# Paleta categórica validada (orden fijo; un color sigue a su zona, no a su rango)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTRO = "#898781"
SECUENCIAL = [[0, "#f3f8fe"], [0.15, "#cde2fb"], [0.35, "#86b6ef"], [0.55, "#3987e5"],
              [0.75, "#1c5cab"], [1, "#0d366b"]]
DIVERGENTE = [[0, "#2a78d6"], [0.5, "#f0efec"], [1, "#e34948"]]
TINTA, TINTA_2, MUTED, GRID, EJE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SUPERFICIE = "#fcfcfb"
FUENTE = 'system-ui, -apple-system, "Segoe UI", sans-serif'
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def color_zona(zonas: list[str], z) -> str:
    try:
        i = zonas.index(z)
    except ValueError:
        return OTRO
    return SERIES[i] if i < len(SERIES) else OTRO


def estilo(fig: go.Figure, x: str | None = None, y: str | None = None, alto: int = 420) -> go.Figure:
    m = fig.layout.margin
    margen = dict(l=m.l if m.l is not None else 60, r=m.r if m.r is not None else 20,
                  t=m.t if m.t is not None else 40, b=m.b if m.b is not None else 50)
    # Con títulos de subgráfica arriba, la leyenda va debajo para no taparlos
    abajo = len(fig.layout.annotations) > 0
    leyenda = (dict(orientation="h", y=-0.38, yanchor="top", x=0) if abajo
               else dict(orientation="h", y=1.02, yanchor="bottom", x=0))
    if abajo:
        margen["b"] = max(margen["b"], 150)
    fig.update_layout(
        template="none", height=alto, font=dict(family=FUENTE, size=12, color=TINTA_2),
        paper_bgcolor=SUPERFICIE, plot_bgcolor=SUPERFICIE, margin=margen,
        legend=dict(**leyenda, font=dict(color=TINTA_2)),
        hoverlabel=dict(font=dict(family=FUENTE)),
    )
    ejes = dict(gridcolor=GRID, linecolor=EJE, zerolinecolor=EJE, tickfont=dict(color=MUTED), automargin=True)
    fig.update_xaxes(**ejes)
    fig.update_yaxes(**ejes)
    if x is not None:
        fig.update_xaxes(title=x)
    if y is not None:
        fig.update_yaxes(title=y)
    return fig


def selector(fig: go.Figure, grupos: list[tuple[str, int]], etiqueta: str = "Zona") -> go.Figure:
    """Agrega un menú que muestra un grupo de trazas a la vez. `grupos` es una lista
    de (nombre, número de trazas) en el mismo orden en que se agregaron las trazas."""
    if len(grupos) <= 1:
        return fig
    total = sum(n for _, n in grupos)
    botones, ini = [], 0
    for nombre, n in grupos:
        vis = [False] * total
        vis[ini:ini + n] = [True] * n
        botones.append(dict(label=f"{etiqueta}: {nombre}", method="update", args=[{"visible": vis}]))
        ini += n
    vis0 = [False] * total
    vis0[:grupos[0][1]] = [True] * grupos[0][1]
    for t, v in zip(fig.data, vis0):
        t.visible = v
    fig.update_layout(
        updatemenus=[dict(buttons=botones, direction="down", x=1, xanchor="right", y=1.0, yanchor="bottom",
                          pad=dict(b=28), bgcolor="#ffffff", bordercolor=EJE, font=dict(color=TINTA))],
        margin=dict(t=max(fig.layout.margin.t or 0, 90)),
    )
    return fig


def caja(nombre: str, fila, color: str, piso: float | None = None) -> go.Box:
    """Boxplot desde percentiles precalculados: caja p25-p75, línea p50, bigotes p10-p90."""
    def v(k):
        x = float(fila[k])
        return max(x, piso) if piso is not None else x
    return go.Box(x=[nombre], q1=[v("p25")], median=[v("p50")], q3=[v("p75")],
                  lowerfence=[v("p10")], upperfence=[v("p90")], name=nombre,
                  marker_color=color, line_width=1.5, showlegend=False,
                  hovertemplate=None)


# --- escala logarítmica con signo (para huecos que pueden ser negativos = solapes) ---
_TICKS_MIN = [0, 1, 10, 60, 240, 1440, 10080, 43200]
_TICKS_TXT = ["0", "1 min", "10 min", "1 h", "4 h", "1 d", "7 d", "30 d"]


def symlog(x):
    x = np.asarray(x, dtype=float)
    return np.sign(x) * np.log10(1 + np.abs(x))


def ejes_symlog(fig: go.Figure, eje: str = "y", maximo: float | None = None) -> go.Figure:
    vals, txt = [], []
    for m, t in zip(_TICKS_MIN, _TICKS_TXT):
        if maximo is not None and m > maximo * 1.5 and m > 60:
            continue
        if m == 0:
            vals.append(0.0)
            txt.append("0")
        else:
            vals += [symlog(m), symlog(-m)]
            txt += [t, "−" + t]
    upd = dict(tickvals=vals, ticktext=txt)
    (fig.update_yaxes if eje == "y" else fig.update_xaxes)(**upd)
    return fig


def sombrear(fig: go.Figure, meses) -> go.Figure:
    """Sombrea los meses marcados como incompletos en una serie de tiempo."""
    for m in sorted(meses):
        fig.add_vrect(x0=m.start_time, x1=(m + 1).start_time, fillcolor=MUTED, opacity=0.15,
                      line_width=0, layer="below")
    return fig


def heatmap_dia_hora(z: np.ndarray, x_horas: list[str], titulo_color: str, colores=None,
                     zmid: float | None = None, visible: bool = True, fmt: str = ".1f") -> go.Heatmap:
    return go.Heatmap(z=z, x=x_horas, y=DIAS, colorscale=colores or SECUENCIAL, zmid=zmid,
                      colorbar=dict(title=dict(text=titulo_color, side="top"), thickness=12, len=0.9), visible=visible,
                      xgap=1, ygap=1, hovertemplate="%{y} %{x}: %{z:" + fmt + "}<extra></extra>")
