"""H. Atributos opcionales: duración y destino por grupo. Categóricas: top N + "otros";
numéricas: bins configurados (o quintiles). Grupos pequeños se agrupan en "otros"."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import figuras as F
from .comun import FIN, Contexto, Registro, tabla_percentiles

SEC = "H. Atributos"
OTROS = "otros"


def agrupar(serie: pd.Series, tipo: str, bins, top_n: int, min_grupo: int) -> pd.Series:
    if tipo == "numerica":
        x = pd.to_numeric(serie, errors="coerce")
        if bins:
            g = pd.cut(x, bins=bins, right=False)
        else:
            g = pd.qcut(x, q=5, duplicates="drop")
        g = g.astype(str).where(x.notna(), "sin dato")
    else:
        g = serie.astype("string").fillna("sin dato").astype(str)
        top = g.value_counts().head(top_n).index
        g = g.where(g.isin(top), OTROS)
    n = g.map(g.value_counts())
    return g.where(n >= min_grupo, OTROS)


def correr(ctx: Contexto, reg: Registro) -> None:
    cfg, est = ctx.cfg, ctx.est
    for a in cfg.atributos:
        col = f"attr_{a.columna}"
        if col not in est.columns:
            reg.aviso(f"El atributo '{a.columna}' no está en los datos; se omite.")
            continue
        e = est.assign(grupo=agrupar(est[col], a.tipo, a.bins, cfg.top_n_categorias, cfg.tamano_min_grupo))
        orden = (sorted(e["grupo"].unique(), key=lambda s: (s in (OTROS, "sin dato"), _clave_orden(s)))
                 if a.tipo == "numerica" else list(e["grupo"].value_counts().index))

        t = tabla_percentiles(e, ["zona", "grupo"], "min")
        t.insert(0, "atributo", a.columna)
        reg.tabla(SEC, f"atributo_{a.columna}_duracion", t,
                  f"Duración (min) por zona y grupo de '{a.columna}'. Grupos con menos de {cfg.tamano_min_grupo} "
                  "estancias se agrupan en 'otros'.")
        des = e.groupby(["zona", "grupo", "destino"]).size().rename("n").reset_index()
        des["proporcion"] = des["n"] / des.groupby(["zona", "grupo"])["n"].transform("sum")
        des.insert(0, "atributo", a.columna)
        reg.tabla(SEC, f"atributo_{a.columna}_destino", des,
                  f"Destino al salir de cada zona por grupo de '{a.columna}' (proporción dentro del grupo).")

        fig, grupos = go.Figure(), []
        for z in ctx.zonas:
            tz = t[t["zona"] == z].set_index("grupo")
            k = 0
            for gname in orden:
                if gname in tz.index:
                    fig.add_trace(F.caja(gname, tz.loc[gname], F.color_zona(ctx.zonas, z), piso=1.0))
                    k += 1
            grupos.append((ctx.nombre(z), k))
        fig.update_yaxes(type="log")
        F.selector(F.estilo(fig, a.columna, "minutos en la zona (escala log)"), grupos)
        reg.fig(SEC, f"Duración por grupo de {a.columna}", fig,
                f"Para la zona elegida, duración por grupo de '{a.columna}': caja p25-p75, mediana, bigotes p10-p90. "
                "Escala logarítmica. Comparar alturas entre grupos; el tamaño de cada grupo está en la tabla.")

        fig, grupos = go.Figure(), []
        for z in ctx.zonas:
            dz = des[des["zona"] == z]
            dests = list(dz.groupby("destino")["n"].sum().sort_values(ascending=False).index)
            for dst in dests:
                dd = dz[dz["destino"] == dst].set_index("grupo").reindex(orden)
                nombre = FIN if dst == FIN else ctx.nombre(dst)
                fig.add_bar(x=orden, y=dd["proporcion"], name=nombre,
                            marker=dict(color=F.MUTED if dst == FIN else F.color_zona(ctx.zonas, dst),
                                        line=dict(color=F.SUPERFICIE, width=1)),
                            hovertemplate="%{x}: %{y:.1%}<extra>" + nombre + "</extra>")
            grupos.append((ctx.nombre(z), len(dests)))
        fig.update_layout(barmode="stack")
        fig.update_yaxes(tickformat=".0%")
        F.selector(F.estilo(fig, a.columna, "proporción de estancias"), grupos)
        reg.fig(SEC, f"Destino por grupo de {a.columna}", fig,
                f"Para la zona elegida, a dónde va cada estancia al salir, por grupo de '{a.columna}'. Cada barra "
                "suma 100 %; gris = el episodio termina en esa zona.")


def _clave_orden(s: str) -> float:
    try:
        return float(s.strip("[(").split(",")[0])
    except ValueError:
        return np.inf
