"""D. Ocupación (censo) por barrido de eventos.

Para intervalos [inicio, fin) ordenados, el censo en el instante t es
  N_inicios(<= t) - N_fines(<= t)
y la integral del censo hasta t (horas-paciente acumuladas) es
  t·N_i(t) - S_i(t) - (t·N_f(t) - S_f(t)),
con S = suma acumulada de los tiempos. Todo sale de searchsorted y cumsum:
O(n log n), sin bucles por hora ni por intervalo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import figuras as F
from .comun import Contexto, Registro, segundos

SEC = "D. Ocupación (censo)"
HORAS = [f"{h:02d}h" for h in range(24)]


class Barrido:
    """Inicios y fines ordenados de una zona, listos para consultar censo e integral."""

    def __init__(self, inicio_s: np.ndarray, fin_s: np.ndarray, origen: float = 0.0):
        ok = ~(np.isnan(inicio_s) | np.isnan(fin_s))
        self.origen = origen
        self.s = np.sort(inicio_s[ok] - origen)
        self.e = np.sort(fin_s[ok] - origen)
        self.cs = np.concatenate([[0.0], np.cumsum(self.s)])
        self.ce = np.concatenate([[0.0], np.cumsum(self.e)])

    def censo(self, t: np.ndarray, excluir_inicio_en_t: bool = False) -> np.ndarray:
        """Intervalos abiertos en t ([inicio, fin) contiene a t). Con `excluir_inicio_en_t`
        no cuenta los que empiezan justo en t (útil para 'cuántos había al llegar')."""
        t = np.asarray(t, dtype=float) - self.origen
        lado = "left" if excluir_inicio_en_t else "right"
        return np.searchsorted(self.s, t, lado) - np.searchsorted(self.e, t, "right")

    def integral(self, t: np.ndarray) -> np.ndarray:
        t = np.asarray(t, dtype=float) - self.origen
        ni = np.searchsorted(self.s, t, "right")
        nf = np.searchsorted(self.e, t, "right")
        return t * ni - self.cs[ni] - (t * nf - self.ce[nf])

    def censo_medio(self, t0: np.ndarray, paso_s: float) -> np.ndarray:
        """Censo medio ponderado por tiempo en cada [t0, t0 + paso)."""
        t0 = np.asarray(t0, dtype=float)
        return (self.integral(t0 + paso_s) - self.integral(t0)) / paso_s


def censo_horario(est: pd.DataFrame, zonas: list[str], t0: pd.Timestamp, t1: pd.Timestamp):
    """Censo por hora y zona entre t0 y t1. Devuelve (tabla larga, barridos por zona)."""
    horas = pd.date_range(t0.floor("h"), t1.floor("h"), freq="h")
    hs = segundos(horas)
    origen = hs[0] if len(hs) else 0.0
    barridos, partes = {}, []
    for z in zonas:
        e = est[est["zona"] == z]
        b = Barrido(segundos(e["inicio"]), segundos(e["fin"]), origen)
        barridos[z] = b
        partes.append(pd.DataFrame({"hora": horas, "zona": z, "censo_inst": b.censo(hs),
                                    "censo_medio": b.censo_medio(hs, 3600.0)}))
    cen = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(
        columns=["hora", "zona", "censo_inst", "censo_medio"])
    return cen, barridos


def correr(ctx: Contexto, reg: Registro) -> None:
    est, cfg = ctx.est, ctx.cfg
    t0, t1 = est["inicio"].min(), est["inicio"].max()
    cen, barridos = censo_horario(est, ctx.zonas, t0, t1)
    cen["completo"] = ctx.completo(cen["hora"])
    ctx.censo = cen
    reg.tabla(SEC, "censo_horario", cen,
              "Censo por hora y zona: censo_inst = personas en la zona al inicio de la hora; censo_medio = promedio "
              "ponderado por tiempo dentro de la hora. 'completo' = la hora cae en un mes no marcado como incompleto.")

    # Censo al momento de entrar (propia zona y zona siguiente), para D y F
    s_in = segundos(est["inicio"])
    est["censo_al_entrar"] = np.nan
    est["censo_siguiente_al_entrar"] = np.nan
    for z, b in barridos.items():
        m = (est["zona"] == z).to_numpy()
        est.loc[m, "censo_al_entrar"] = b.censo(s_in[m], excluir_inicio_en_t=True)
        m2 = (est["siguiente"] == z).fillna(False).to_numpy()
        est.loc[m2, "censo_siguiente_al_entrar"] = b.censo(s_in[m2])

    comp = cen[cen["completo"]].copy()
    comp["dow"] = comp["hora"].dt.dayofweek
    comp["h"] = comp["hora"].dt.hour

    # Serie temporal: media y máximo diario del censo horario
    dia = cen.assign(dia=cen["hora"].dt.floor("D")).groupby(["zona", "dia"])["censo_medio"].agg(["mean", "max"]).reset_index()
    fig, grupos = go.Figure(), []
    for z in ctx.zonas:
        dz = dia[dia["zona"] == z]
        col = F.color_zona(ctx.zonas, z)
        fig.add_scatter(x=dz["dia"], y=dz["max"], mode="lines", line=dict(color=col, width=1), opacity=0.35,
                        name="máximo horario del día", hovertemplate="%{x|%Y-%m-%d}: máx %{y:.1f}<extra></extra>")
        fig.add_scatter(x=dz["dia"], y=dz["mean"], mode="lines", line=dict(color=col, width=2),
                        name="media del día", hovertemplate="%{x|%Y-%m-%d}: media %{y:.1f}<extra></extra>")
        n = 2
        if z in cfg.capacidades:
            fig.add_scatter(x=[dia["dia"].min(), dia["dia"].max()], y=[cfg.capacidades[z]] * 2, mode="lines",
                            line=dict(color=F.TINTA, width=1.5, dash="dash"), name="capacidad de referencia")
            n += 1
        grupos.append((ctx.nombre(z), n))
    F.sombrear(fig, ctx.meses_incompletos)
    F.selector(F.estilo(fig, None, "personas en la zona", alto=440), grupos)
    reg.fig(SEC, "Censo por zona en el tiempo", fig,
            "Línea gruesa: censo medio de cada día (promedio de los censos horarios). Línea tenue: el máximo horario "
            "de ese día. Línea punteada: capacidad de referencia, solo si está configurada. Zonas sombreadas: meses "
            "incompletos. Los primeros días pueden subestimar el censo porque no se ven estancias que empezaron "
            "antes del extracto. El detalle hora a hora está en la tabla censo_horario.")

    # Heatmaps hora x día de semana: media y p90
    g = comp.groupby(["zona", "dow", "h"])["censo_medio"]
    hm = pd.concat([g.mean().rename("media"), g.quantile(0.9).rename("p90")], axis=1).reset_index()
    reg.tabla(SEC, "censo_hora_dia", hm, "Censo medio y p90 por zona, día de la semana (0 = lunes) y hora, "
              "solo meses completos.")
    fig, grupos = make_subplots(rows=1, cols=2, subplot_titles=("Censo medio", "Censo p90"), horizontal_spacing=0.17), []
    for z in ctx.zonas:
        hz = hm[hm["zona"] == z]
        for i, c in enumerate(("media", "p90")):
            z_ = hz.pivot(index="dow", columns="h", values=c).reindex(index=range(7), columns=range(24)).to_numpy()
            tr = F.heatmap_dia_hora(z_, HORAS, "personas")
            tr.colorbar.x = 0.43 if i == 0 else 1.0
            fig.add_trace(tr, row=1, col=i + 1)
        grupos.append((ctx.nombre(z), 2))
    F.selector(F.estilo(fig, alto=420), grupos)
    reg.fig(SEC, "Censo por día de la semana y hora", fig,
            "Cada celda resume el censo (promedio ponderado dentro de la hora) de todas las semanas completas para "
            "ese día y hora. Izquierda: promedio. Derecha: p90, es decir, el nivel que se supera en una de cada "
            "diez semanas. Celdas oscuras = más personas en la zona a esa hora.")

    # Distribución del censo horario
    fig, grupos, filas = go.Figure(), [], []
    for z in ctx.zonas:
        v = comp.loc[comp["zona"] == z, "censo_medio"].to_numpy()
        if v.size == 0:
            continue
        hi = np.ceil(v.max()) + 1
        anchos = max(1.0, np.ceil(hi / 60))
        cnt, bordes = np.histogram(v, bins=np.arange(0, hi + anchos, anchos))
        p = cnt / cnt.sum()
        fig.add_bar(x=bordes[:-1], y=p, width=anchos, marker_color=F.color_zona(ctx.zonas, z), showlegend=False,
                    hovertemplate="censo %{x:.0f}: %{y:.2%} de las horas<extra></extra>")
        n = 1
        if z in cfg.capacidades:
            fig.add_scatter(x=[cfg.capacidades[z]] * 2, y=[0, p.max()], mode="lines", name="capacidad de referencia",
                            line=dict(color=F.TINTA, dash="dash"))
            n += 1
        grupos.append((ctx.nombre(z), n))
        q = np.quantile(v, [0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99])
        filas.append({"zona": z, "nombre": ctx.nombre(z), "horas": v.size, "media": v.mean(),
                      **{f"p{p_}": x for p_, x in zip([10, 25, 50, 75, 90, 95, 99], q)},
                      "capacidad": cfg.capacidades.get(z, np.nan),
                      "p_horas_sobre_capacidad": float((v > cfg.capacidades[z]).mean()) if z in cfg.capacidades else np.nan})
    fig.update_yaxes(tickformat=".0%")
    F.selector(F.estilo(fig, "censo medio en la hora", "proporción de horas"), grupos)
    reg.fig(SEC, "Distribución del censo horario", fig,
            "Proporción de horas (meses completos) en que la zona tuvo cada nivel de censo. Una distribución "
            "ancha o con cola a la derecha indica horas con mucha más gente que lo habitual. Línea punteada: "
            "capacidad de referencia si está configurada.")
    reg.tabla(SEC, "censo_distribucion", pd.DataFrame(filas),
              "Percentiles del censo horario por zona (meses completos) y proporción de horas sobre la capacidad "
              "de referencia, si está configurada.")

    # Censo al llegar, por hora de entrada (lo que "ve" quien entra)
    e = est[ctx.completo(est["inicio"])].assign(h=lambda x: x["inicio"].dt.hour)
    g = e.groupby(["zona", "h"])["censo_al_entrar"]
    ll = pd.concat([g.median().rename("p50"), g.quantile(0.9).rename("p90")], axis=1).reset_index()
    reg.tabla(SEC, "censo_al_llegar", ll, "Por zona y hora de entrada: mediana y p90 del censo de la zona en el "
              "instante en que entra cada estancia (sin contarse a sí misma).")
    fig, grupos = go.Figure(), []
    for z in ctx.zonas:
        lz = ll[ll["zona"] == z].set_index("h").reindex(range(24))
        col = F.color_zona(ctx.zonas, z)
        fig.add_scatter(x=HORAS, y=lz["p90"], mode="lines", line=dict(color=col, width=2, dash="dot"), name="p90")
        fig.add_scatter(x=HORAS, y=lz["p50"], mode="lines+markers", line=dict(color=col, width=2),
                        marker=dict(size=8), name="mediana")
        grupos.append((ctx.nombre(z), 2))
    F.selector(F.estilo(fig, "hora de entrada", "personas ya en la zona"), grupos)
    reg.fig(SEC, "Censo encontrado al llegar, por hora", fig,
            "Para cada estancia se cuenta cuántas personas ya estaban en la zona en el instante de su entrada. "
            "Se muestra la mediana y el p90 por hora de entrada (meses completos). A diferencia del censo medio, "
            "esto pondera cada hora por cuántas personas llegan en ella.")

    little(ctx, reg, comp)


def little(ctx: Contexto, reg: Registro, comp: pd.DataFrame) -> None:
    """Ley de Little por zona y mes: L (censo medio observado) vs λ·W."""
    est = ctx.est[ctx.completo(ctx.est["inicio"])].copy()
    est["mes"] = est["inicio"].dt.to_period("M")
    comp = comp.assign(mes=comp["hora"].dt.to_period("M"))
    L = comp.groupby(["zona", "mes"]).agg(L=("censo_medio", "mean"), horas=("censo_medio", "size"))
    g = est.groupby(["zona", "mes"])
    lw = pd.DataFrame({"entradas": g.size(), "W_h": g["min"].mean() / 60})
    t = L.join(lw, how="inner").reset_index()
    t["lambda_por_h"] = t["entradas"] / t["horas"]
    t["lambda_W"] = t["lambda_por_h"] * t["W_h"]
    t["L_sobre_lambdaW"] = t["L"] / t["lambda_W"]
    t["nombre"] = t["zona"].map(ctx.nombre)
    t["mes"] = t["mes"].astype(str)
    reg.tabla(SEC, "little_zona_mes", t,
              "Ley de Little por zona y mes completo: L = censo medio observado; λ = entradas por hora; W = duración "
              "media (h) de las estancias que entran en el mes; L_sobre_lambdaW cercano a 1 = consistente.")
    fig = go.Figure()
    for z in ctx.zonas:
        tz = t[t["zona"] == z]
        if tz.empty:
            continue
        fig.add_scatter(x=tz["lambda_W"], y=tz["L"], mode="markers", name=ctx.nombre(z),
                        marker=dict(size=9, color=F.color_zona(ctx.zonas, z), line=dict(color=F.SUPERFICIE, width=2)),
                        customdata=tz["mes"], hovertemplate="%{customdata}<br>λ·W %{x:.1f} · L %{y:.1f}<extra>"
                        + ctx.nombre(z) + "</extra>")
    if not t.empty:
        m = float(np.nanmax(t[["L", "lambda_W"]].to_numpy())) * 1.05
        fig.add_scatter(x=[0, m], y=[0, m], mode="lines", line=dict(color=F.MUTED, dash="dash", width=1),
                        name="L = λ·W", hoverinfo="skip")
    reg.fig(SEC, "Ley de Little por zona y mes", F.estilo(fig, "λ·W (entradas por hora × duración media en h)",
                                                         "L observado (censo medio)", alto=460),
            "Cada punto es una zona en un mes completo. Si el registro es consistente, L ≈ λ·W y los puntos caen "
            "sobre la diagonal. Puntos lejos de la diagonal pueden venir de estancias que cruzan meses, de "
            "registros abiertos o de recortes del extracto.")
