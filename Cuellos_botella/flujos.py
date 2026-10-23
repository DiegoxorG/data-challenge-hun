"""C. Por zona: duración de las estancias y flujo de entradas y salidas en el día y la semana."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import figuras as F
from .comun import Contexto, Registro, cuantiles_rejilla, tabla_percentiles

SEC = "C. Por zona: duración y flujo"
PISO_MIN = 1.0   # en escala log, las duraciones < 1 min se dibujan en 1 min


def etiquetas_bin(minutos: int) -> list[str]:
    return [f"{m // 60:02d}:{m % 60:02d}" for m in range(0, 1440, minutos)]


def bin_del_dia(fechas: pd.Series, minutos: int) -> pd.Series:
    return (fechas.dt.hour * 60 + fechas.dt.minute) // minutos


def perfil_flujo(ctx: Contexto) -> pd.DataFrame:
    """Entradas y salidas promedio por día, por zona, día de semana y franja del día (meses completos)."""
    est, mb = ctx.est, ctx.cfg.minutos_bin_perfil
    dias = ctx.dias_por_dow(est["inicio"].min(), est["inicio"].max())
    partes = []
    for col, nombre in (("inicio", "entradas"), ("fin", "salidas")):
        e = est[ctx.completo(est[col]) & (est[col] <= est["inicio"].max())]
        c = e.groupby([e["zona"], e[col].dt.dayofweek.rename("dow"), bin_del_dia(e[col], mb).rename("bin")]).size()
        partes.append(c.rename(nombre))
    idx = pd.MultiIndex.from_product([ctx.zonas, range(7), range(1440 // mb)], names=["zona", "dow", "bin"])
    p = pd.concat(partes, axis=1).reindex(idx, fill_value=0).fillna(0).reset_index()
    n_dias = p["dow"].map(dias).replace(0, np.nan)
    p["entradas_prom"] = p["entradas"] / n_dias
    p["salidas_prom"] = p["salidas"] / n_dias
    p["desbalance_prom"] = p["entradas_prom"] - p["salidas_prom"]
    return p


def correr(ctx: Contexto, reg: Registro) -> None:
    est, mb = ctx.est, ctx.cfg.minutos_bin_perfil
    etq = etiquetas_bin(mb)

    # Duración por zona
    pct = tabla_percentiles(est, "zona", "min")
    pct.insert(1, "nombre", pct["zona"].map(ctx.nombre))
    reg.tabla(SEC, "duracion_percentiles", pct, "Duración de las estancias por zona en minutos: n, media y "
              "percentiles p10 a p99.")
    fig = go.Figure()
    for z in ctx.zonas:
        r = pct[pct["zona"] == z]
        if not r.empty:
            fig.add_trace(F.caja(ctx.nombre(z), r.iloc[0], F.color_zona(ctx.zonas, z), piso=PISO_MIN))
    fig.update_yaxes(type="log")
    reg.fig(SEC, "Duración de las estancias por zona", F.estilo(fig, None, "minutos (escala log)"),
            "Caja = p25 a p75, línea interior = mediana, bigotes = p10 a p90 de la duración de las estancias en "
            "cada zona. Escala logarítmica: cada marca multiplica por 10. Duraciones menores a 1 min se dibujan en "
            "1 min. Valores exactos en duracion_percentiles.")

    fig = go.Figure()
    for z in ctx.zonas:
        x, q = cuantiles_rejilla(est.loc[est["zona"] == z, "min"].to_numpy())
        if x.size:
            fig.add_scatter(x=np.maximum(x, PISO_MIN), y=q, mode="lines", name=ctx.nombre(z),
                            line=dict(color=F.color_zona(ctx.zonas, z), width=2),
                            hovertemplate="%{y:.0%} dura ≤ %{x:.0f} min<extra>" + ctx.nombre(z) + "</extra>")
    fig.update_xaxes(type="log")
    fig.update_yaxes(tickformat=".0%")
    reg.fig(SEC, "Distribución acumulada de la duración (ECDF)", F.estilo(fig, "minutos (escala log)",
                                                                         "proporción de estancias con duración ≤ x"),
            "Para cada zona, la curva indica qué proporción de las estancias dura como máximo x minutos. Una curva "
            "más a la derecha = estancias más largas; un tramo plano = pocas estancias con esa duración; dos "
            "subidas separadas = dos grupos de duraciones distintas.")

    # Entradas y salidas por día de semana y franja
    p = perfil_flujo(ctx)
    p.insert(1, "nombre", p["zona"].map(ctx.nombre))
    p["franja"] = p["bin"].map(dict(enumerate(etq)))
    reg.tabla(SEC, "flujo_hora_dia", p, f"Por zona, día de semana (0 = lunes) y franja de {mb} min: entradas y "
              "salidas totales y promedio por día (meses completos); desbalance = entradas − salidas.")

    fig = make_subplots(rows=1, cols=2, subplot_titles=("Entradas promedio por día", "Salidas promedio por día"),
                        horizontal_spacing=0.17)
    grupos = []
    for z in ctx.zonas:
        pz = p[p["zona"] == z]
        for i, c in enumerate(("entradas_prom", "salidas_prom")):
            mat = pz.pivot(index="dow", columns="bin", values=c).reindex(index=range(7)).to_numpy()
            tr = F.heatmap_dia_hora(mat, etq, "por día", fmt=".2f")
            tr.colorbar.x = 0.43 if i == 0 else 1.0
            fig.add_trace(tr, row=1, col=i + 1)
        grupos.append((ctx.nombre(z), 2))
    F.selector(F.estilo(fig, alto=420), grupos)
    reg.fig(SEC, "Entradas y salidas por día de la semana y hora", fig,
            f"Promedio por día de estancias que entran (izquierda) y salen (derecha) de la zona en cada franja de "
            f"{mb} min, por día de la semana (meses completos). Comparar ambos mapas permite ver franjas donde "
            f"entra más gente de la que sale.")

    tip = p.groupby(["zona", "bin"])[["entradas_prom", "salidas_prom", "desbalance_prom"]].mean().reset_index()
    fig, grupos = go.Figure(), []
    for z in ctx.zonas:
        tz = tip[tip["zona"] == z]
        col = np.where(tz["desbalance_prom"] >= 0, F.SERIES[7], F.SERIES[0])
        fig.add_bar(x=etq, y=tz["desbalance_prom"], marker_color=col, showlegend=False,
                    hovertemplate="%{x}: %{y:+.2f} por día<extra></extra>")
        grupos.append((ctx.nombre(z), 1))
    F.selector(F.estilo(fig, "franja del día", "entradas − salidas (promedio por día)"), grupos)
    reg.fig(SEC, "Desbalance entradas − salidas por hora", fig,
            "Para el día típico (promedio de todos los días de la semana), entradas menos salidas en cada franja. "
            "Rojo = entran más de las que salen (la zona se llena en esa franja); azul = salen más de las que "
            "entran (se vacía).")

    fig, grupos = go.Figure(), []
    for z in ctx.zonas:
        tz = tip[tip["zona"] == z]
        col = F.color_zona(ctx.zonas, z)
        fig.add_scatter(x=etq, y=tz["entradas_prom"].cumsum(), mode="lines", name="entradas acumuladas",
                        line=dict(color=col, width=2))
        fig.add_scatter(x=etq, y=tz["salidas_prom"].cumsum(), mode="lines", name="salidas acumuladas",
                        line=dict(color=col, width=2, dash="dash"))
        grupos.append((ctx.nombre(z), 2))
    F.selector(F.estilo(fig, "franja del día", "acumulado desde las 00:00 (promedio por día)"), grupos)
    reg.fig(SEC, "Entradas vs. salidas acumuladas en el día típico", fig,
            "Curvas acumuladas desde la medianoche del promedio diario de entradas (continua) y salidas "
            "(punteada). La distancia vertical entre ambas en cada hora es cuánto ha crecido la zona desde la "
            "medianoche; la distancia horizontal aproxima cuánto tarda en salir el volumen que entró.")
