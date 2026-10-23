"""G. Tiempo: series diarias y semanales de entradas, mediana de duración y censo,
y perfil por mes del año. Los meses incompletos se sombrean."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import figuras as F
from .comun import Contexto, Registro

SEC = "G. Tiempo"
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def series(ctx: Contexto) -> tuple[pd.DataFrame, pd.DataFrame]:
    est = ctx.est
    dia = est["inicio"].dt.floor("D")
    g = est.groupby(["zona", dia])
    d = pd.DataFrame({"entradas": g.size(), "mediana_min": g["min"].median()})
    d.index.names = ["zona", "fecha"]
    c = ctx.censo.assign(fecha=ctx.censo["hora"].dt.floor("D")).groupby(["zona", "fecha"])["censo_medio"].mean()
    d = d.join(c.rename("censo_medio"), how="outer").reset_index()
    d["entradas"] = d["entradas"].fillna(0)

    sem = est.assign(fecha=est["inicio"].dt.to_period("W-SUN").dt.start_time)
    g = sem.groupby(["zona", "fecha"])
    w = pd.DataFrame({"entradas": g.size(), "mediana_min": g["min"].median()})
    cw = ctx.censo.assign(fecha=ctx.censo["hora"].dt.to_period("W-SUN").dt.start_time).groupby(["zona", "fecha"])["censo_medio"].mean()
    w = w.join(cw.rename("censo_medio"), how="outer").reset_index()
    w["entradas"] = w["entradas"].fillna(0)
    return d, w


def _fig_dia_semana(ctx: Contexto, d: pd.DataFrame, w: pd.DataFrame, col: str, y: str, escala: float = 1.0,
                    log: bool = False) -> go.Figure:
    fig = go.Figure()
    zonas = [z for z in ctx.zonas if z in set(d["zona"])]
    for serie, df_, vis in (("Diaria", d, False), ("Semanal", w, True)):
        for z in zonas:
            dz = df_[df_["zona"] == z]
            fig.add_scatter(x=dz["fecha"], y=dz[col] * escala, mode="lines", name=ctx.nombre(z), visible=vis,
                            line=dict(color=F.color_zona(ctx.zonas, z), width=1.2 if serie == "Diaria" else 2),
                            legendgroup=z, hovertemplate="%{x|%Y-%m-%d}: %{y:.2f}<extra>" + ctx.nombre(z) + "</extra>")
    n = len(zonas)
    fig.update_layout(updatemenus=[dict(type="buttons", direction="right", x=1, xanchor="right", y=1.2, active=1,
                                        buttons=[dict(label="Diaria", method="update", args=[{"visible": [True] * n + [False] * n}]),
                                                 dict(label="Semanal", method="update", args=[{"visible": [False] * n + [True] * n}])])],
                      margin=dict(t=80))
    F.sombrear(fig, ctx.meses_incompletos)
    if log:
        fig.update_yaxes(type="log")
    return F.estilo(fig, None, y, alto=420)


def correr(ctx: Contexto, reg: Registro) -> None:
    d, w = series(ctx)
    reg.tabla(SEC, "serie_diaria", d, "Por zona y día: entradas, mediana de duración (min) de las estancias que "
              "entran ese día y censo medio del día.")
    reg.tabla(SEC, "serie_semanal", w, "Igual que serie_diaria, por semana (lunes a domingo, fecha = lunes).")
    sombra = " Las franjas grises son meses marcados como incompletos." if ctx.meses_incompletos else ""
    reg.fig(SEC, "Entradas en el tiempo", _fig_dia_semana(ctx, d, w, "entradas", "entradas (estancias que empiezan)"),
            "Número de estancias que entran a cada zona por día o por semana (botones arriba a la derecha)." + sombra)
    reg.fig(SEC, "Mediana de duración en el tiempo", _fig_dia_semana(ctx, d, w, "mediana_min", "mediana de duración (h, escala log)", 1 / 60, log=True),
            "Mediana de la duración de las estancias según el día o la semana en que entran. Las estancias que "
            "entran al final del extracto pueden verse más cortas porque las largas aún no habían terminado." + sombra)
    reg.fig(SEC, "Censo medio en el tiempo", _fig_dia_semana(ctx, d, w, "censo_medio", "censo medio"),
            "Censo medio (promedio de los censos horarios) por día o por semana." + sombra)

    # Perfil por mes del año (solo meses completos)
    dd = d[ctx.completo(d["fecha"])].assign(mes=lambda x: x["fecha"].dt.month)
    p = dd.groupby(["zona", "mes"]).agg(entradas_por_dia=("entradas", "mean"), mediana_min=("mediana_min", "median"),
                                        censo_medio=("censo_medio", "mean"), dias=("fecha", "nunique")).reset_index()
    p["nombre_mes"] = p["mes"].map(lambda m: MESES[m - 1])
    reg.tabla(SEC, "perfil_mensual", p, "Por zona y mes del año (meses completos): entradas promedio por día, "
              "mediana diaria de la mediana de duración (min), censo medio y días observados.")
    fig = make_subplots(rows=1, cols=3, subplot_titles=("Entradas por día", "Mediana de duración (h, log)", "Censo medio"))
    for z in ctx.zonas:
        pz = p[p["zona"] == z].set_index("mes").reindex(range(1, 13))
        for i, (c, k) in enumerate((("entradas_por_dia", 1), ("mediana_min", 1 / 60), ("censo_medio", 1))):
            fig.add_scatter(x=MESES, y=pz[c] * k, mode="lines+markers", name=ctx.nombre(z), legendgroup=z,
                            showlegend=i == 0, line=dict(color=F.color_zona(ctx.zonas, z), width=2), marker=dict(size=8),
                            row=1, col=i + 1)
    fig.update_yaxes(type="log", col=2)
    reg.fig(SEC, "Perfil por mes del año", F.estilo(fig, alto=440),
            "Promedio por mes calendario de todos los años disponibles (solo meses completos): entradas por día, "
            "mediana de duración y censo medio. Con pocos años, cada punto depende de muy pocos meses.")
