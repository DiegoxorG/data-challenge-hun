"""B. Episodios y trayectorias.

- Episodio: segmentos de una persona unidos si se solapan o el hueco es <= umbral
  (gaps and islands vectorizado), o la columna `caso` si está configurada.
- Estancia: segmentos seguidos de la misma zona dentro de un episodio, unidos.
  Es la unidad de análisis por zona (evita contar varias entradas por tramos de registro).
- Recorte: si una estancia sigue abierta cuando empieza la siguiente del mismo
  episodio, su fin se corta al inicio de la siguiente.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import figuras as F
from .comun import FIN, Contexto, Registro, segundos

SEC = "B. Episodios y trayectorias"
MAX_PASOS_SECUENCIA = 8


def asignar_episodios(seg: pd.DataFrame, umbral_min: float, usar_caso: bool = False) -> pd.Series:
    """Id de episodio por segmento (alineado con seg.index)."""
    d = seg.sort_values(["persona", "inicio", "fin"])
    if usar_caso and "caso" in d.columns:
        clave = d["persona"].astype(str) + "|" + d["caso"].astype(str)
        # Segmentos sin caso quedan como episodios propios
        clave = clave.where(d["caso"].notna(), "sin_caso|" + pd.Series(np.arange(len(d)), index=d.index).astype(str))
        ep = pd.Series(pd.factorize(clave)[0], index=d.index)
        return ep.reindex(seg.index)
    pc = pd.factorize(d["persona"])[0]
    s, e = segundos(d["inicio"]), segundos(d["fin"])
    prev = pd.Series(e).groupby(pc).cummax().groupby(pc).shift(1).to_numpy()
    nuevo = np.isnan(prev) | (s > prev + umbral_min * 60)
    return pd.Series(np.cumsum(nuevo) - 1, index=d.index).reindex(seg.index)


def construir_estancias(seg: pd.DataFrame) -> pd.DataFrame:
    """Une segmentos consecutivos (por inicio) de la misma zona dentro de cada episodio
    y calcula el orden, la zona siguiente, el hueco de transición y el fin recortado."""
    d = seg.sort_values(["episodio", "inicio", "fin"]).reset_index(drop=True)
    zona = d["zona"].to_numpy()
    ep = d["episodio"].to_numpy()
    bloque = np.ones(len(d), dtype=bool)
    if len(d) > 1:
        bloque[1:] = (zona[1:] != zona[:-1]) | (ep[1:] != ep[:-1])
    d["estancia"] = np.cumsum(bloque) - 1

    attrs = [c for c in d.columns if c.startswith("attr_")]
    agg = {"persona": ("persona", "first"), "episodio": ("episodio", "first"), "zona": ("zona", "first"),
           "inicio": ("inicio", "min"), "fin_original": ("fin", "max"), "n_segmentos": ("zona", "size")}
    agg.update({a: (a, "first") for a in attrs})
    est = d.groupby("estancia", sort=True).agg(**agg).reset_index()
    est = est.sort_values(["episodio", "inicio", "fin_original"]).reset_index(drop=True)

    g = est.groupby("episodio", sort=False)
    est["paso"] = g.cumcount()
    est["n_estancias"] = g["zona"].transform("size")
    est["siguiente"] = g["zona"].shift(-1)
    est["anterior"] = g["zona"].shift(1)
    est["inicio_siguiente"] = g["inicio"].shift(-1)

    corta = est["inicio_siguiente"].notna() & (est["inicio_siguiente"] < est["fin_original"])
    est["recortada"] = corta
    est["fin_recortado"] = est["fin_original"].where(~corta, est[["inicio_siguiente", "inicio"]].max(axis=1))
    est["min_original"] = (est["fin_original"] - est["inicio"]).dt.total_seconds() / 60
    est["min_recortado"] = (est["fin_recortado"] - est["inicio"]).dt.total_seconds() / 60
    # Hueco entre salir de esta zona (fin registrado) y entrar a la siguiente; negativo = solape
    est["hueco_min"] = (est["inicio_siguiente"] - est["fin_original"]).dt.total_seconds() / 60
    est["destino"] = est["siguiente"].fillna(FIN)
    return est


def episodios_irregulares(est: pd.DataFrame, orden: list[str]) -> pd.Series:
    """True por episodio si su secuencia de estancias no avanza en el orden del flujo:
    una zona se repite (urgencias → hospitalización → urgencias) o una zona aparece después
    de otra que va más adelante (hospitalización → urgencias). `orden` es el orden de las
    zonas en el flujo (el de zonas_agrupar en el config); las zonas fuera de él solo cuentan
    si se repiten. Es la única definición: el resumen seguro y el test de equivalencia la usan."""
    d = est.sort_values(["episodio", "paso"])
    g = d.groupby("episodio", sort=True)
    repetida = g["zona"].nunique() < g.size()
    rango = d["zona"].map({z: i for i, z in enumerate(orden)}).astype(float)
    retrocede = (rango < rango.groupby(d["episodio"]).cummax()).groupby(d["episodio"]).any()
    return (repetida | retrocede.reindex(repetida.index, fill_value=False)).rename("irregular")


def construir_episodios(est: pd.DataFrame, etiquetas: dict) -> pd.DataFrame:
    g = est.groupby("episodio", sort=True)
    epi = pd.DataFrame({
        "persona": g["persona"].first(), "inicio": g["inicio"].min(), "fin": g["fin_original"].max(),
        "n_estancias": g.size(), "zona_inicial": g["zona"].first(), "zona_final": g["zona"].last(),
    })
    corto = est[est["paso"] < MAX_PASOS_SECUENCIA]
    sec = corto["zona"].map(etiquetas).fillna(corto["zona"]).astype(str).groupby(corto["episodio"]).agg(" → ".join)
    epi["secuencia"] = sec.where(epi["n_estancias"] <= MAX_PASOS_SECUENCIA, sec + " → …")
    epi["min"] = (epi["fin"] - epi["inicio"]).dt.total_seconds() / 60
    epi = epi.reset_index().sort_values(["persona", "inicio"])
    # Siguiente episodio de la misma persona (para reconsultas)
    gp = epi.groupby("persona", sort=False)
    epi["hueco_siguiente_h"] = (gp["inicio"].shift(-1) - epi["fin"]).dt.total_seconds() / 3600
    epi["zona_inicial_siguiente"] = gp["zona_inicial"].shift(-1)
    return epi.reset_index(drop=True)


def censo_medio_global(inicio: pd.Series, fin: pd.Series, t0: pd.Timestamp, t1: pd.Timestamp) -> float:
    """Censo medio en [t0, t1) = horas-paciente dentro del rango / horas del rango."""
    a = np.maximum(segundos(inicio), segundos(pd.Series([t0]))[0])
    b = np.minimum(segundos(fin), segundos(pd.Series([t1]))[0])
    dur = (t1 - t0).total_seconds()
    return float(np.clip(b - a, 0, None).sum() / dur) if dur > 0 else np.nan


def correr(ctx: Contexto, reg: Registro) -> None:
    cfg = ctx.cfg
    ctx.seg["episodio"] = asignar_episodios(ctx.seg, cfg.umbral_min, usar_caso=bool(cfg.caso))
    est = construir_estancias(ctx.seg)
    est["fin"] = est["fin_recortado"] if cfg.recortar_al_siguiente else est["fin_original"]
    est["min"] = est["min_recortado"] if cfg.recortar_al_siguiente else est["min_original"]
    ctx.est = est
    ctx.epi = construir_episodios(est, ctx.etiquetas)
    epi = ctx.epi
    # Con todas las estancias, antes de excluir las largas
    epi["irregular"] = episodios_irregulares(est, list(cfg.zonas_agrupar)).reindex(epi["episodio"]).to_numpy()

    modo = (f"columna de caso '{cfg.caso}'" if cfg.caso else f"umbral de {cfg.umbral_min:g} min entre segmentos")
    reg.tabla(SEC, "episodios_resumen", pd.DataFrame([
        {"indicador": "episodios", "valor": len(epi)},
        {"indicador": "estancias", "valor": len(est)},
        {"indicador": "segmentos", "valor": len(ctx.seg)},
        {"indicador": "p_episodios_una_estancia", "valor": float((epi["n_estancias"] == 1).mean())},
        # Ahí _episodios.sql y la 25 miden distinto que esta herramienta (ver test_equivalencia_sql.py)
        {"indicador": "p_episodios_irregulares",
         "valor": float(epi["irregular"].mean())},
        {"indicador": "p_estancias_recortables", "valor": float(est["recortada"].mean())},
        {"indicador": "recorte_aplicado", "valor": int(cfg.recortar_al_siguiente)},
    ]), f"Totales de episodios, estancias y segmentos. Episodios definidos por {modo}.")

    # Secuencias más frecuentes
    top = epi["secuencia"].value_counts(normalize=True).head(20).rename("proporcion").reset_index()
    top.columns = ["secuencia", "proporcion"]
    top["n"] = (top["proporcion"] * len(epi)).round().astype(int)
    reg.tabla(SEC, "secuencias_top", top, "Las 20 secuencias de zonas más frecuentes y su proporción de episodios.")
    t = top.iloc[::-1]
    fig = go.Figure(go.Bar(x=t["proporcion"], y=t["secuencia"], orientation="h", marker_color=F.SERIES[0],
                           hovertemplate="%{y}<br>%{x:.2%} de los episodios<extra></extra>"))
    fig.update_xaxes(tickformat=".0%")
    fig.update_layout(margin=dict(l=320))
    reg.fig(SEC, "Secuencias de zonas más frecuentes", F.estilo(fig, "proporción de episodios", None, alto=560),
            f"Cada barra es una secuencia de zonas (estancias en orden de inicio) y la proporción de episodios que "
            f"la siguen. Episodios definidos por {modo}. Secuencias de más de {MAX_PASOS_SECUENCIA} pasos se "
            f"cortan con '…'.")

    # Estancias por episodio
    k = epi["n_estancias"].clip(upper=10).value_counts(normalize=True).sort_index()
    fig = go.Figure(go.Bar(x=[str(i) if i < 10 else "10+" for i in k.index], y=k.values, marker_color=F.SERIES[0],
                           hovertemplate="%{x} estancias: %{y:.2%}<extra></extra>"))
    fig.update_yaxes(tickformat=".0%")
    reg.fig(SEC, "Número de estancias por episodio", F.estilo(fig, "estancias en el episodio", "proporción de episodios"),
            "Distribución de cuántas estancias (zonas consecutivas distintas) tiene cada episodio. "
            "1 = el episodio ocurre en una sola zona.")

    comparar_recorte(ctx, reg)
    if cfg.muestra_carriles > 0:
        carriles(ctx, reg)
    excluir_largas(ctx, reg)


def excluir_largas(ctx: Contexto, reg: Registro) -> None:
    """Saca del resto del reporte (censo, duraciones, transiciones…) las estancias más largas
    que el límite de su zona, como la consulta 25 con urgencias > 7 días y hospitalización > 90.
    Los episodios ya están construidos, así que no cambian: un episodio con una estancia
    excluida sigue contando como episodio."""
    lim = ctx.cfg.excluir_estancias_largas
    if not lim:
        return
    est = ctx.est
    tope = est["zona"].map(lim).astype(float) * 1440   # minutos; NaN = zona sin límite
    fuera = (est["min"] > tope).fillna(False).to_numpy(dtype=bool)
    filas = []
    for z, dias in lim.items():
        m = (est["zona"] == z).to_numpy()
        filas.append({"zona": z, "nombre": ctx.nombre(z), "limite_dias": dias, "estancias": int(m.sum()),
                      "excluidas": int((m & fuera).sum()),
                      "p_excluidas": float((m & fuera).sum() / m.sum()) if m.sum() else float("nan")})
    reg.tabla(SEC, "estancias_excluidas", pd.DataFrame(filas),
              "Estancias más largas que el límite de su zona (excluir_estancias_largas), que quedan fuera del "
              "censo y de las demás secciones. La duración usada es la del resto del reporte (con o sin recorte).")
    ctx.est = est[~fuera].reset_index(drop=True)


def comparar_recorte(ctx: Contexto, reg: Registro) -> None:
    est = ctx.est
    t0, t1 = est["inicio"].min(), est["inicio"].max()
    filas = []
    for z, e in est.groupby("zona", sort=False):
        f = {"zona": z, "nombre": ctx.nombre(z), "n": len(e), "p_recortadas": float(e["recortada"].mean())}
        for ver in ("original", "recortado"):
            m = e[f"min_{ver}"]
            f.update({f"p50_min_{ver}": m.median(), f"p90_min_{ver}": m.quantile(0.9),
                      f"horas_paciente_{ver}": m.sum() / 60,
                      f"censo_medio_{ver}": censo_medio_global(e["inicio"], e[f"fin_{ver}"], t0, t1)})
        filas.append(f)
    comp = pd.DataFrame(filas)
    reg.tabla(SEC, "comparativa_recorte", comp,
              "Por zona: duración p50/p90, horas-paciente y censo medio sin recorte (original) y con recorte "
              "al inicio de la estancia siguiente. p_recortadas = proporción de estancias afectadas.")
    comp = comp.set_index("zona")
    comp = comp.loc[[z for z in ctx.zonas if z in comp.index]]
    nombres = [ctx.nombre(z) for z in comp.index]
    fig = make_subplots(rows=1, cols=3, subplot_titles=("Mediana de duración (h)", "p90 de duración (h)", "Censo medio"))
    for i, (ver, txt, col) in enumerate([("original", "sin recorte", F.SERIES[0]), ("recortado", "con recorte", F.SERIES[1])]):
        fig.add_bar(x=nombres, y=comp[f"p50_min_{ver}"] / 60, name=txt, marker_color=col, row=1, col=1,
                    legendgroup=ver, hovertemplate="%{x}: %{y:.2f} h<extra>" + txt + "</extra>")
        fig.add_bar(x=nombres, y=comp[f"p90_min_{ver}"] / 60, name=txt, marker_color=col, row=1, col=2,
                    legendgroup=ver, showlegend=False, hovertemplate="%{x}: %{y:.2f} h<extra>" + txt + "</extra>")
        fig.add_bar(x=nombres, y=comp[f"censo_medio_{ver}"], name=txt, marker_color=col, row=1, col=3,
                    legendgroup=ver, showlegend=False, hovertemplate="%{x}: %{y:.1f}<extra>" + txt + "</extra>")
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.05)
    estado = "aplicado en el resto del reporte" if ctx.cfg.recortar_al_siguiente else "NO aplicado en el resto del reporte"
    reg.fig(SEC, "Con y sin recorte al inicio de la zona siguiente", F.estilo(fig, alto=420),
            "Compara, por zona, la mediana y el p90 de duración y el censo medio con el fin registrado (sin recorte) "
            "y con el fin cortado cuando empieza la estancia siguiente del mismo episodio (con recorte). "
            f"Si las barras coinciden, el recorte casi no cambia nada en esa zona. Recorte {estado}.")


def carriles(ctx: Contexto, reg: Registro) -> None:
    """Diagrama de carriles con una muestra aleatoria de episodios (nivel individuo: solo salida local)."""
    epi = ctx.epi[ctx.epi["n_estancias"] >= 2]
    if epi.empty:
        return
    muestra = epi.sample(min(ctx.cfg.muestra_carriles, len(epi)), random_state=0)["episodio"]
    e = ctx.est[ctx.est["episodio"].isin(muestra)].copy()
    base = e.groupby("episodio")["inicio"].transform("min")
    e["h0"] = (e["inicio"] - base).dt.total_seconds() / 3600
    e["h"] = (e["fin"] - e["inicio"]).dt.total_seconds() / 3600
    orden = {ep: i for i, ep in enumerate(muestra)}
    e["fila"] = e["episodio"].map(orden)
    fig = go.Figure()
    for z in ctx.zonas:
        ez = e[e["zona"] == z]
        if ez.empty:
            continue
        fig.add_bar(base=ez["h0"], x=ez["h"].clip(lower=0.02), y=ez["fila"], orientation="h", name=ctx.nombre(z),
                    marker_color=F.color_zona(ctx.zonas, z), opacity=0.85,
                    hovertemplate="desde %{base:.1f} h, dura %{x:.1f} h<extra>" + ctx.nombre(z) + "</extra>")
    fig.update_layout(barmode="overlay")
    fig.update_yaxes(showticklabels=False)
    reg.fig(SEC, "Carriles de una muestra aleatoria de episodios", F.estilo(fig, "horas desde el inicio del episodio",
                                                                            "episodio (muestra)", alto=600),
            "Cada fila es un episodio elegido al azar (con dos o más estancias); cada barra es una estancia, "
            "coloreada por zona, desde su inicio hasta su fin. Barras superpuestas = estancias que se solapan. "
            "Vista a nivel de individuo: solo para revisión local, no se resume ni se comparte.")
