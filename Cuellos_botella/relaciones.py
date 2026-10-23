"""F. Relaciones de la duración en la zona con la hora y el día de entrada, el censo
(propio y de la zona siguiente) al entrar, la carga de entradas recientes y el destino."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import figuras as F
from .comun import FIN, Contexto, Registro, segundos, tabla_percentiles

SEC = "F. Relaciones para buscar acumulación"
HORAS = [f"{h:02d}h" for h in range(24)]


def entradas_recientes(est: pd.DataFrame, ventana_h: float) -> np.ndarray:
    """Por estancia: cuántas estancias entraron a la misma zona en las `ventana_h` horas previas."""
    out = np.full(len(est), np.nan)
    s = segundos(est["inicio"])
    zona = est["zona"].to_numpy()
    w = ventana_h * 3600
    for z in pd.unique(zona):
        m = zona == z
        t = np.sort(s[m])
        out[m] = np.searchsorted(t, s[m], "left") - np.searchsorted(t, s[m] - w, "left")
    return out


def por_cuantiles(df: pd.DataFrame, col: str, q: int) -> pd.DataFrame:
    """Agrupa `col` en cuantiles (bins con límites legibles) y resume la duración."""
    d = df[df[col].notna()]
    if d[col].nunique() < 2:
        return pd.DataFrame()
    b = pd.qcut(d[col], q=q, duplicates="drop")
    t = d.groupby(b, observed=True)["min"].agg(n="size", p50="median", p75=lambda x: x.quantile(0.75)).reset_index()
    minimo = d[col].min()
    t["bin"] = [f"{max(i.left, minimo):.0f}–{i.right:.0f}" for i in t[col]]
    t["orden"] = range(len(t))
    return t.drop(columns=[col])


def correr(ctx: Contexto, reg: Registro) -> None:
    cfg = ctx.cfg
    est = ctx.est
    est["carga_reciente"] = entradas_recientes(est, cfg.ventana_carga_h)
    e = est[ctx.completo(est["inicio"])].assign(dow=lambda x: x["inicio"].dt.dayofweek,
                                                h=lambda x: x["inicio"].dt.hour,
                                                h_salida=lambda x: x["fin"].dt.hour)

    # Duración por hora x día de entrada
    t = tabla_percentiles(e, ["zona", "dow", "h"], "min", [50, 75])
    reg.tabla(SEC, "rel_hora_dia", t, "Duración (min) por zona, día de semana de entrada (0 = lunes) y hora de "
              "entrada: n, media, p50 y p75 (meses completos).")
    fig, grupos = make_subplots(rows=1, cols=2, subplot_titles=("Mediana (h)", "p75 (h)"), horizontal_spacing=0.17), []
    for z in ctx.zonas:
        tz = t[t["zona"] == z]
        for i, c in enumerate(("p50", "p75")):
            mat = tz.pivot(index="dow", columns="h", values=c).reindex(index=range(7), columns=range(24)).to_numpy() / 60
            tr = F.heatmap_dia_hora(mat, HORAS, "horas", fmt=".2f")
            tr.colorbar.x = 0.43 if i == 0 else 1.0
            fig.add_trace(tr, row=1, col=i + 1)
        grupos.append((ctx.nombre(z), 2))
    F.selector(F.estilo(fig, alto=420), grupos)
    reg.fig(SEC, "Duración según día y hora de entrada", fig,
            "Mediana (izquierda) y p75 (derecha) de la duración en la zona, en horas, según el día y la hora en que "
            "entra la estancia. Celdas oscuras = quienes entran en ese momento se quedan más tiempo.")

    # Duración por hora de entrada vs hora de salida
    he = e.groupby(["zona", "h"])["min"].median().rename("p50_por_hora_entrada")
    hs = e.groupby(["zona", "h_salida"])["min"].median().rename("p50_por_hora_salida")
    hs.index.names = ["zona", "h"]
    hh = pd.concat([he, hs], axis=1).reset_index()
    reg.tabla(SEC, "rel_hora_entrada_salida", hh, "Mediana de duración (min) por zona según la hora de entrada y "
              "según la hora de salida.")
    fig, grupos = go.Figure(), []
    for z in ctx.zonas:
        hz = hh[hh["zona"] == z].set_index("h").reindex(range(24))
        col = F.color_zona(ctx.zonas, z)
        fig.add_scatter(x=HORAS, y=hz["p50_por_hora_entrada"] / 60, mode="lines+markers", name="por hora de entrada",
                        line=dict(color=col, width=2), marker=dict(size=8))
        fig.add_scatter(x=HORAS, y=hz["p50_por_hora_salida"] / 60, mode="lines", name="por hora de salida",
                        line=dict(color=col, width=2, dash="dash"))
        grupos.append((ctx.nombre(z), 2))
    F.selector(F.estilo(fig, "hora", "mediana de duración (h)"), grupos)
    reg.fig(SEC, "Duración según hora de entrada y de salida", fig,
            "Mediana de la duración en la zona agrupando por la hora en que se entra (continua) y por la hora en "
            "que se sale (punteada). Si las salidas largas se concentran en ciertas horas, la curva punteada sube "
            "en esas horas.")

    # Censo propio y de la zona siguiente al entrar
    partes = []
    for var, txt in (("censo_al_entrar", "propio"), ("censo_siguiente_al_entrar", "zona siguiente")):
        for z in ctx.zonas:
            q = por_cuantiles(e[e["zona"] == z], var, cfg.cuantiles_censo)
            if not q.empty:
                partes.append(q.assign(zona=z, variable=txt))
    if partes:
        rc = pd.concat(partes, ignore_index=True)
        reg.tabla(SEC, "rel_censo", rc, "Duración (min, p50 y p75) por cuantil del censo al entrar: de la propia "
                  "zona y de la zona a la que pasa después (solo estancias con zona siguiente).")
        fig = make_subplots(rows=1, cols=2, subplot_titles=("Censo de la propia zona al entrar",
                                                            "Censo de la zona siguiente al entrar"))
        grupos = []
        for z in ctx.zonas:
            n = 0
            col = F.color_zona(ctx.zonas, z)
            for i, txt in enumerate(("propio", "zona siguiente")):
                rz = rc[(rc["zona"] == z) & (rc["variable"] == txt)]
                fig.add_scatter(x=rz["bin"], y=rz["p50"] / 60, mode="lines+markers", name="mediana",
                                line=dict(color=col, width=2), marker=dict(size=8), showlegend=i == 0,
                                row=1, col=i + 1, customdata=rz["n"], hovertemplate="censo %{x}: %{y:.2f} h<extra>mediana</extra>")
                fig.add_scatter(x=rz["bin"], y=rz["p75"] / 60, mode="lines", name="p75",
                                line=dict(color=col, width=2, dash="dot"), showlegend=i == 0, row=1, col=i + 1,
                                hovertemplate="censo %{x}: %{y:.2f} h<extra>p75</extra>")
                n += 2
            grupos.append((ctx.nombre(z), n))
        F.selector(F.estilo(fig, alto=420), grupos)
        fig.update_xaxes(title="cuantil del censo (personas)")
        fig.update_yaxes(title="duración (h)", col=1)
        reg.fig(SEC, "Duración según el censo al entrar", fig,
                f"Las estancias de la zona se agrupan en {cfg.cuantiles_censo} cuantiles según cuántas personas "
                "había al entrar en la propia zona (izquierda) o en la zona a la que pasan después (derecha). Para "
                "cada grupo, mediana y p75 de la duración en horas. Una curva que sube indica que se tarda más "
                "cuando esa zona está más llena; es una asociación, no prueba causa.")

    # Carga de entradas recientes
    partes = [por_cuantiles(e[e["zona"] == z], "carga_reciente", cfg.cuantiles_censo).assign(zona=z) for z in ctx.zonas]
    partes = [p for p in partes if "bin" in p.columns]
    if partes:
        rk = pd.concat(partes, ignore_index=True)
        reg.tabla(SEC, "rel_carga", rk, f"Duración (min, p50 y p75) por cuantil de entradas a la misma zona en las "
                  f"{cfg.ventana_carga_h:g} h previas.")
        fig, grupos = go.Figure(), []
        for z in ctx.zonas:
            rz = rk[rk["zona"] == z]
            col = F.color_zona(ctx.zonas, z)
            fig.add_scatter(x=rz["bin"], y=rz["p50"] / 60, mode="lines+markers", name="mediana",
                            line=dict(color=col, width=2), marker=dict(size=8))
            fig.add_scatter(x=rz["bin"], y=rz["p75"] / 60, mode="lines", name="p75", line=dict(color=col, width=2, dash="dot"))
            grupos.append((ctx.nombre(z), 2))
        F.selector(F.estilo(fig, f"entradas a la zona en las {cfg.ventana_carga_h:g} h previas (cuantiles)", "duración (h)"),
                   grupos)
        reg.fig(SEC, "Duración según la carga de entradas recientes", fig,
                f"Estancias agrupadas en cuantiles según cuántas entradas tuvo la misma zona en las "
                f"{cfg.ventana_carga_h:g} h previas a su llegada. Mediana y p75 de la duración por grupo.")

    # Destino
    d = tabla_percentiles(e, ["zona", "destino"], "min")
    d["nombre_destino"] = d["destino"].map(lambda x: FIN if x == FIN else ctx.nombre(x))
    reg.tabla(SEC, "rel_destino", d, "Duración (min) en la zona según a qué zona pasa después o si el episodio "
              "termina ahí.")
    fig, grupos = go.Figure(), []
    for z in ctx.zonas:
        dz = d[d["zona"] == z].sort_values("n", ascending=False).head(10)
        for _, r in dz.iterrows():
            col = F.MUTED if r["destino"] == FIN else F.color_zona(ctx.zonas, r["destino"])
            fig.add_trace(F.caja(r["nombre_destino"], r, col, piso=1.0))
        grupos.append((ctx.nombre(z), len(dz)))
    fig.update_yaxes(type="log")
    F.selector(F.estilo(fig, "destino al salir de la zona", "minutos en la zona (escala log)"), grupos)
    reg.fig(SEC, "Duración según el destino", fig,
            "Para la zona elegida, distribución de la duración (caja p25-p75, mediana, bigotes p10-p90) separando "
            "las estancias según la zona a la que pasan después (color = zona destino) o si el episodio termina "
            "ahí (gris). Escala logarítmica.")
