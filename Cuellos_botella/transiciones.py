"""E. Transiciones entre zonas: matriz origen→destino, Sankey, hueco/solape entre
salir de una zona y entrar a la siguiente, y reconsultas entre episodios."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import figuras as F
from .comun import DIAS, FIN, Contexto, Registro, tabla_percentiles

SEC = "E. Transiciones entre zonas"
TOP_TRANSICIONES = 12


def matriz(est: pd.DataFrame) -> pd.DataFrame:
    """Conteos y probabilidad por fila de cada par origen → destino (destino FIN = termina ahí)."""
    m = est.groupby(["zona", "destino"]).size().rename("n").reset_index()
    m["probabilidad"] = m["n"] / m.groupby("zona")["n"].transform("sum")
    return m.rename(columns={"zona": "origen"})


def correr(ctx: Contexto, reg: Registro) -> None:
    est = ctx.est
    nom = lambda z: FIN if z == FIN else ctx.nombre(z)  # noqa: E731

    m = matriz(est)
    m["nombre_origen"] = m["origen"].map(nom)
    m["nombre_destino"] = m["destino"].map(nom)
    reg.tabla(SEC, "transiciones_matriz", m, "Conteos y probabilidades (por zona de origen) de pasar a cada zona "
              "destino dentro del mismo episodio; '(fin del episodio)' = el episodio termina en esa zona.")
    destinos = [z for z in ctx.zonas if z in set(m["destino"])] + [FIN]
    for valor, titulo, fmt in (("probabilidad", "probabilidades", ".1%"), ("n", "conteos", ",.0f")):
        piv = m.pivot(index="origen", columns="destino", values=valor).reindex(
            index=[z for z in ctx.zonas if z in set(m["origen"])], columns=destinos)
        txt = [[("" if np.isnan(v) else format(v, fmt)) for v in fila] for fila in piv.to_numpy()]
        fig = go.Figure(go.Heatmap(z=piv.to_numpy(), x=[nom(z) for z in piv.columns], y=[nom(z) for z in piv.index],
                                   text=txt, texttemplate="%{text}", colorscale=F.SECUENCIAL, xgap=1, ygap=1,
                                   colorbar=dict(title=valor, thickness=12),
                                   hovertemplate="%{y} → %{x}: %{text}<extra></extra>"))
        fig.update_yaxes(autorange="reversed")
        reg.fig(SEC, f"Matriz origen → destino ({titulo})", F.estilo(fig, "destino", "origen", alto=460),
                "Filas = zona de la que sale la estancia; columnas = zona de la estancia siguiente en el mismo "
                "episodio, o '(fin del episodio)'. "
                + ("Cada fila suma 100 %." if valor == "probabilidad" else "Número de estancias por par."))

    sankey(ctx, reg)

    # Hueco entre salir y entrar a la siguiente (negativo = la siguiente empezó antes de cerrar esta)
    t = est[est["siguiente"].notna()].copy()
    if t.empty:
        return
    t["par"] = t["zona"].map(ctx.nombre) + " → " + t["siguiente"].map(ctx.nombre)
    hu = tabla_percentiles(t, ["zona", "siguiente", "par"], "hueco_min")
    hu["p_solape"] = t.groupby(["zona", "siguiente", "par"])["hueco_min"].apply(lambda x: (x < 0).mean()).to_numpy()
    hu["p_contiguo"] = t.groupby(["zona", "siguiente", "par"])["hueco_min"].apply(lambda x: (x == 0).mean()).to_numpy()
    hu = hu.sort_values("n", ascending=False)
    reg.tabla(SEC, "transiciones_hueco", hu, "Por transición: minutos entre el fin registrado de la zona de origen "
              "y el inicio de la siguiente (negativo = solape). p_solape = proporción con solape; p_contiguo = "
              "proporción con hueco exactamente 0.")
    top = hu.head(TOP_TRANSICIONES)
    fig = go.Figure()
    for _, r in top.iterrows():
        q = {k: F.symlog(r[k]) for k in ("p10", "p25", "p50", "p75", "p90")}
        fig.add_trace(F.caja(r["par"], q, F.color_zona(ctx.zonas, r["zona"])))
    F.ejes_symlog(fig, "y", maximo=float(np.nanmax(np.abs(top[["p10", "p90"]].to_numpy()))))
    fig.update_layout(margin=dict(b=160))
    reg.fig(SEC, "Hueco o solape entre zonas consecutivas", F.estilo(fig, None, "minutos (escala log con signo)", alto=520),
            "Para las transiciones más frecuentes (color = zona de origen): caja p25-p75, línea = mediana, bigotes "
            "p10-p90 del tiempo entre el fin registrado en la zona de origen y el inicio en la siguiente. Arriba de "
            "0 = hueco sin registro; abajo de 0 = la siguiente zona empezó antes de cerrar la anterior (solape). "
            "El eje usa escala logarítmica a ambos lados del 0.")

    # Hueco mediano por hora y por día de la salida
    pares = list(top["par"].head(6))
    t6 = t[t["par"].isin(pares)].assign(h=lambda x: x["fin_original"].dt.hour,
                                        dow=lambda x: x["fin_original"].dt.dayofweek)
    por_h = t6.groupby(["par", "h"])["hueco_min"].median().rename("p50_min").reset_index()
    por_d = t6.groupby(["par", "dow"])["hueco_min"].median().rename("p50_min").reset_index()
    reg.tabla(SEC, "transiciones_hueco_hora_dia",
              pd.concat([por_h.assign(dimension="hora", valor=por_h["h"]),
                         por_d.assign(dimension="dia_semana", valor=por_d["dow"])])[["par", "dimension", "valor", "p50_min"]],
              "Mediana del hueco (min) por hora y por día de la semana (0 = lunes) en que se registra la salida de "
              "la zona de origen, para las transiciones más frecuentes.")
    for dim, df_, xs, xt in (("h", por_h, list(range(24)), [f"{h:02d}h" for h in range(24)]),
                             ("dow", por_d, list(range(7)), DIAS)):
        fig = go.Figure()
        for i, par in enumerate(pares):
            d = df_[df_["par"] == par].set_index(dim).reindex(xs)
            fig.add_scatter(x=xt, y=F.symlog(d["p50_min"]), mode="lines+markers", name=par,
                            line=dict(color=F.SERIES[i], width=2), marker=dict(size=8),
                            customdata=d["p50_min"], hovertemplate="%{x}: %{customdata:.0f} min<extra>" + par + "</extra>")
        F.ejes_symlog(fig, "y")
        quien = "la hora" if dim == "h" else "el día de la semana"
        reg.fig(SEC, f"Hueco mediano según {quien} de salida", F.estilo(fig, f"{quien.split(' ', 1)[1]} en que sale de la zona de origen",
                                                                         "mediana del hueco (escala log con signo)"),
                f"Mediana del hueco entre zonas según {quien} en que se registra la salida de la zona de origen, "
                "para las transiciones más frecuentes. Si la mediana sube en ciertas franjas, el paso a la zona "
                "siguiente tarda más cuando se sale a esas horas.")

    reconsultas(ctx, reg)


def sankey(ctx: Contexto, reg: Registro) -> None:
    k = ctx.cfg.pasos_sankey
    est = ctx.est
    e = est[est["paso"] < k][["episodio", "paso", "zona", "n_estancias"]].copy()
    visibles = set(ctx.zonas[:8])
    e["z"] = e["zona"].where(e["zona"].isin(visibles), "__otras__")
    nombre = lambda z: "otras zonas" if z == "__otras__" else ctx.nombre(z)  # noqa: E731
    e = e.sort_values(["episodio", "paso"])
    e["z_sig"] = e.groupby("episodio")["z"].shift(-1)
    ult = e["z_sig"].isna()
    corta = ult & (e["n_estancias"] > k)
    e["z_sig"] = np.where(corta, "__sigue__", np.where(ult, "__fin__", e["z_sig"]))
    links = e.groupby(["paso", "z", "z_sig"]).size().rename("n").reset_index()

    nodos, idx = [], {}

    def nodo(paso, z):
        key = (paso, z)
        if key not in idx:
            idx[key] = len(nodos)
            if z == "__fin__":
                txt, col = FIN, F.MUTED
            elif z == "__sigue__":
                txt, col = f"continúa (más de {k} pasos)", F.EJE
            else:
                txt, col = f"{paso + 1}. {nombre(z)}", F.color_zona(ctx.zonas, z) if z != "__otras__" else F.OTRO
            nodos.append((txt, col))
        return idx[key]

    src, dst, val = [], [], []
    for _, r in links.iterrows():
        src.append(nodo(r["paso"], r["z"]))
        dst.append(nodo(r["paso"] + 1, r["z_sig"]))
        val.append(r["n"])
    fig = go.Figure(go.Sankey(
        node=dict(label=[n[0] for n in nodos], color=[n[1] for n in nodos], pad=14, thickness=14,
                  line=dict(color=F.SUPERFICIE, width=1)),
        link=dict(source=src, target=dst, value=val, color="rgba(137,135,129,0.25)"),
        valueformat=",.0f"))
    reg.fig(SEC, "Trayectorias de los episodios (Sankey)", F.estilo(fig, alto=640),
            f"Flujo de episodios por sus primeras {k} estancias. Cada columna es un paso (1 = primera zona del "
            f"episodio); el grosor de cada banda es el número de episodios que pasa de una zona a la siguiente. "
            f"'(fin del episodio)' = termina ahí; 'continúa' = tiene más de {k} pasos. Zonas fuera de las 8 más "
            f"frecuentes se agrupan en 'otras zonas'.")


def reconsultas(ctx: Contexto, reg: Registro) -> None:
    """Hueco entre el fin de un episodio y el inicio del siguiente de la misma persona."""
    w = ctx.cfg.ventana_reconsulta_h
    epi = ctx.epi
    r = epi[epi["hueco_siguiente_h"].notna() & (epi["hueco_siguiente_h"] <= w)].copy()
    resumen = pd.DataFrame([{"ventana_h": w, "episodios": len(epi), "con_otro_en_ventana": len(r),
                             "proporcion": len(r) / len(epi) if len(epi) else np.nan}])
    if r.empty:
        reg.tabla(SEC, "reconsultas_resumen", resumen, f"Episodios seguidos de otro de la misma persona en ≤ {w:g} h.")
        return
    r["par"] = r["zona_final"].map(ctx.nombre) + " → " + r["zona_inicial_siguiente"].map(ctx.nombre)
    t = tabla_percentiles(r, ["zona_final", "zona_inicial_siguiente", "par"], "hueco_siguiente_h", [25, 50, 75])
    t["proporcion_de_episodios_que_terminan_en_origen"] = t["n"] / t["zona_final"].map(epi["zona_final"].value_counts())
    t = t.sort_values("n", ascending=False)
    reg.tabla(SEC, "reconsultas_resumen", resumen, f"Episodios seguidos de otro de la misma persona en ≤ {w:g} h.")
    reg.tabla(SEC, "reconsultas_pares", t, f"Por par zona final → zona inicial del episodio siguiente (≤ {w:g} h): "
              "n y percentiles del hueco en horas.")
    bordes = np.unique(np.concatenate([np.array([0, 1, 2, 4, 6, 12, 24, 36, 48, 72, 168]), [w]]))
    bordes = bordes[bordes <= w]
    fig = go.Figure()
    for i, par in enumerate(t["par"].head(5)):
        x = r.loc[r["par"] == par, "hueco_siguiente_h"]
        cnt, _ = np.histogram(x, bins=bordes)
        etq = [f"{a:g}-{b:g} h" for a, b in zip(bordes[:-1], bordes[1:])]
        fig.add_bar(x=etq, y=cnt / max(cnt.sum(), 1), name=par, marker_color=F.SERIES[i],
                    hovertemplate="%{x}: %{y:.1%}<extra>" + par + "</extra>")
    fig.update_yaxes(tickformat=".0%")
    fig.update_layout(barmode="group")
    reg.fig(SEC, "Reconsultas: hueco hasta el siguiente episodio", F.estilo(fig, "horas entre episodios",
                                                                           "proporción dentro del par"),
            f"Para episodios seguidos de otro de la misma persona en ≤ {w:g} h (fuera del umbral de unión), "
            "distribución del hueco por par zona final → zona inicial siguiente (los 5 pares más frecuentes). "
            "Huecos concentrados en ciertas horas pueden ser flujos que el umbral de episodio separa.")
