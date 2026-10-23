"""A. Calidad de datos: nulos, filas inválidas, duplicados, solapes, cobertura mensual
y duraciones extremas. Devuelve los segmentos válidos y los meses incompletos."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import figuras as F
from .comun import Registro, segundos
from .config import Config

SEC = "A. Calidad de datos"
FRANJAS_MIN = [0, 1, 5, 15, 60, 240, 720, 1440, 4320, 10080, 43200, np.inf]
FRANJAS_TXT = ["<1 min", "1-5 min", "5-15 min", "15 min-1 h", "1-4 h", "4-12 h", "12-24 h",
               "1-3 d", "3-7 d", "7-30 d", ">30 d"]


def detectar_solapes(df: pd.DataFrame, max_zonas: int = 40) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Solapes entre segmentos de la misma persona sin comparar pares (O(n·zonas)).

    Un segmento "se solapa" si empieza antes de que termine algún segmento previo
    (en orden de inicio) de la misma persona. Para la misma zona se usa el máximo
    acumulado del fin por (persona, zona); para otras zonas, un máximo acumulado
    por zona arrastrado dentro de la persona.

    Devuelve (flags por segmento alineados con df.index, tabla de pares de zonas).
    """
    d = df.sort_values(["persona", "inicio", "fin"])
    pc = pd.factorize(d["persona"])[0]
    zonas, zc = np.unique(d["zona"].astype(str).to_numpy(), return_inverse=True)
    s, e = segundos(d["inicio"]), segundos(d["fin"])

    # Misma zona
    clave = pc.astype(np.int64) * len(zonas) + zc
    cm = pd.Series(e).groupby(clave).cummax()
    prev = cm.groupby(clave).shift(1).to_numpy()
    misma = s < prev
    solape_misma_min = np.where(misma, (np.fmin(prev, e) - s) / 60, np.nan)

    pares = []
    for z in range(len(zonas)):
        if misma[zc == z].any():
            pares.append(pd.DataFrame({"zona_previa": zonas[z], "zona_posterior": zonas[z],
                                       "min": solape_misma_min[misma & (zc == z)]}))

    # Entre zonas distintas (limitado a las zonas más frecuentes)
    frec = np.bincount(zc, minlength=len(zonas))
    top = np.argsort(-frec)[:max_zonas]
    otra = np.zeros(len(d), dtype=bool)
    pcs = pd.Series(pc)
    for z in top:
        v = pd.Series(np.where(zc == z, e, np.nan))
        acum = v.groupby(pc).cummax().groupby(pc).ffill()
        prev_z = acum.groupby(pcs).shift(1).to_numpy()
        m = (zc != z) & (s < prev_z)
        if m.any():
            otra |= m
            pares.append(pd.DataFrame({"zona_previa": zonas[z], "zona_posterior": zonas[zc[m]],
                                       "min": (np.fmin(prev_z[m], e[m]) - s[m]) / 60}))

    flags = pd.DataFrame({"solape_misma_zona": misma, "solape_otra_zona": otra}, index=d.index)
    if pares:
        p = pd.concat(pares, ignore_index=True)
        tabla = (p.groupby(["zona_previa", "zona_posterior"])["min"]
                 .agg(n="size", p50_min="median", p90_min=lambda x: x.quantile(0.9)).reset_index())
    else:
        tabla = pd.DataFrame(columns=["zona_previa", "zona_posterior", "n", "p50_min", "p90_min"])
    return flags.reindex(df.index), tabla


def cobertura_mensual(df: pd.DataFrame, frac: float, cobertura_min: float) -> pd.DataFrame:
    """Filas, personas y días con datos por mes; marca meses incompletos."""
    if df.empty:
        return pd.DataFrame(columns=["mes", "filas", "personas", "dias_con_datos", "dias_mes",
                                     "incompleto", "motivo"])
    mes = df["inicio"].dt.to_period("M")
    g = df.groupby(mes)
    cob = pd.DataFrame({"filas": g.size(), "personas": g["persona"].nunique(),
                        "dias_con_datos": g["inicio"].apply(lambda x: x.dt.normalize().nunique())})
    rango = pd.period_range(mes.min(), mes.max(), freq="M")
    cob = cob.reindex(rango, fill_value=0)
    cob.index.name = "mes"
    cob["dias_mes"] = [p.days_in_month for p in cob.index]

    mediana = cob["filas"].median()
    baja = cob["filas"] < frac * mediana
    # Fracción del mes calendario cubierta por el rango de datos (solo afecta primer y último mes)
    t0, t1 = df["inicio"].min(), df["inicio"].max()
    frac_cal = pd.Series(1.0, index=cob.index)
    p0, p1 = cob.index[0], cob.index[-1]
    largo0 = (p0 + 1).start_time - p0.start_time
    frac_cal[p0] = ((p0 + 1).start_time - t0) / largo0
    largo1 = (p1 + 1).start_time - p1.start_time
    frac_cal[p1] = min(frac_cal[p1], (t1 - p1.start_time) / largo1) if p1 != p0 else (t1 - t0) / largo1
    parcial = frac_cal < cobertura_min

    cob["fraccion_calendario"] = frac_cal.round(3)
    cob["filas_vs_mediana"] = (cob["filas"] / mediana).round(3) if mediana else np.nan
    cob["incompleto"] = baja | parcial
    cob["motivo"] = np.select([baja & parcial, baja, parcial],
                              ["pocas filas y rango parcial", "pocas filas frente a la mediana",
                               "el rango de datos no cubre el mes completo"], default="")
    return cob.reset_index().assign(mes=lambda x: x["mes"].astype(str))


def analizar(df: pd.DataFrame, tipos: pd.DataFrame, cfg: Config, reg: Registro, etq: dict | None = None):
    etq = etq or {}
    nom = lambda z: etq.get(z, str(z))  # noqa: E731
    n = len(df)
    nulo_clave = df[["persona", "zona", "inicio", "fin"]].isna().any(axis=1)
    invertido = ~nulo_clave & (df["fin"] < df["inicio"])
    cero = ~nulo_clave & (df["fin"] == df["inicio"])
    dup = df.duplicated(["persona", "zona", "inicio", "fin"], keep="first") & ~nulo_clave
    validos = df[~nulo_clave & ~invertido & ~dup].copy()

    flags, pares = detectar_solapes(validos, cfg.max_zonas_solape)
    validos = validos.join(flags)

    def fila(ind, k, base, desc):
        return {"indicador": ind, "n": int(k), "base": int(base), "proporcion": k / base if base else np.nan,
                "descripcion": desc}
    resumen = pd.DataFrame([
        fila("filas_entrada", n, n, "filas tras aplicar rango de fechas y zonas excluidas"),
        fila("clave_nula", nulo_clave.sum(), n, "persona, zona, inicio o fin nulo o no interpretable"),
        fila("fin_antes_de_inicio", invertido.sum(), n, "fin < inicio (se descartan)"),
        fila("duracion_cero", cero.sum(), n, "fin = inicio (se conservan)"),
        fila("duplicadas", dup.sum(), n, "misma persona, zona, inicio y fin (se descarta la copia)"),
        fila("filas_validas", len(validos), n, "filas que entran al análisis"),
        fila("solape_misma_zona", flags["solape_misma_zona"].sum(), len(validos),
             "segmentos que empiezan antes de que termine otro de la misma persona y zona"),
        fila("solape_otra_zona", flags["solape_otra_zona"].sum(), len(validos),
             "segmentos que empiezan antes de que termine otro de la misma persona en otra zona"),
    ])
    reg.tabla(SEC, "calidad_resumen", resumen, "Conteos y proporciones de filas inválidas, duplicadas y con solape.")
    reg.tabla(SEC, "calidad_nulos_tipos", tipos, "Tipo leído, nulos y fechas no interpretables por columna de entrada.")

    # Avisos
    for ind, txt in [("clave_nula", "Hay filas con persona, zona o fechas nulas o no interpretables; se descartan."),
                     ("fin_antes_de_inicio", "Hay filas con fin anterior al inicio; se descartan."),
                     ("duplicadas", "Hay filas duplicadas exactas; se descarta la copia.")]:
        if resumen.set_index("indicador").loc[ind, "n"] > 0:
            reg.aviso(txt)

    # Figura: nulos por columna e indicadores de filas
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Nulos o no interpretables por columna",
                                                        "Filas inválidas, duplicadas y con solape"))
    t = tipos.assign(p=(tipos["nulos"] + tipos["no_interpretables"]) / max(n, 1))
    fig.add_bar(x=t["p"], y=t["columna"], orientation="h", marker_color=F.SERIES[0], row=1, col=1,
                hovertemplate="%{y}: %{x:.2%}<extra></extra>", showlegend=False)
    r = resumen[~resumen["indicador"].isin(["filas_entrada", "filas_validas"])]
    fig.add_bar(x=r["proporcion"], y=r["indicador"], orientation="h", marker_color=F.SERIES[0], row=1, col=2,
                hovertemplate="%{y}: %{x:.2%}<extra></extra>", showlegend=False)
    fig.update_xaxes(tickformat=".0%", rangemode="tozero")
    if t["p"].max() == 0:
        fig.update_xaxes(range=[0, 0.05], row=1, col=1)
    reg.fig(SEC, "Nulos, filas inválidas y solapes", F.estilo(fig, alto=380),
            "Izquierda: proporción de filas con la columna nula o con fecha que no se pudo interpretar. "
            "Derecha: proporción de filas en cada situación (los solapes se miden sobre las filas válidas). "
            "Las barras largas señalan problemas de registro que conviene revisar antes de leer el resto.")

    # Pares de solape
    if not pares.empty:
        base = validos["zona"].astype(str).value_counts()
        pares["proporcion_de_posterior"] = pares["n"] / pares["zona_posterior"].map(base)
        pares["nombre_previa"] = pares["zona_previa"].map(nom)
        pares["nombre_posterior"] = pares["zona_posterior"].map(nom)
        reg.tabla(SEC, "solapes_pares", pares,
                  "Solapes por par de zonas: la zona_posterior empieza antes de que termine la zona_previa "
                  "(misma persona). Minutos de solape p50 y p90.")
        piv = pares.pivot(index="zona_previa", columns="zona_posterior", values="proporcion_de_posterior")
        fig = go.Figure(go.Heatmap(z=piv.to_numpy(), x=[nom(z) for z in piv.columns], y=[nom(z) for z in piv.index],
                                   colorscale=F.SECUENCIAL, xgap=1, ygap=1, colorbar=dict(title="proporción", thickness=12),
                                   hovertemplate="previa %{y} → posterior %{x}: %{z:.2%}<extra></extra>"))
        reg.fig(SEC, "Matriz de solapes entre zonas", F.estilo(fig, "zona que empieza (posterior)", "zona abierta (previa)"),
                "Cada celda es la proporción de segmentos de la zona de la columna que empiezan mientras la misma "
                "persona sigue con un segmento abierto en la zona de la fila. La diagonal es el solape dentro de la "
                "misma zona.")

    # Cobertura mensual
    cob = cobertura_mensual(validos, cfg.mes_incompleto_frac, cfg.mes_cobertura_min)
    reg.tabla(SEC, "cobertura_mensual", cob,
              "Filas, personas y días con datos por mes; 'incompleto' marca meses con pocas filas frente a la "
              "mediana o cuyo rango de datos no cubre el mes calendario.")
    meses_inc = {pd.Period(m, "M") for m in cob.loc[cob["incompleto"], "mes"]}
    if meses_inc:
        reg.aviso("Hay meses marcados como incompletos (ver tabla cobertura_mensual); se sombrean en las series "
                  "y se excluyen de perfiles, censo agregado y ley de Little.")
    if not cob.empty:
        col = np.where(cob["incompleto"], F.OTRO, F.SERIES[0])
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                            subplot_titles=("Filas por mes", "Personas distintas por mes"))
        fig.add_bar(x=cob["mes"], y=cob["filas"], marker_color=col, row=1, col=1, showlegend=False,
                    customdata=cob["motivo"], hovertemplate="%{x}: %{y}<br>%{customdata}<extra></extra>")
        fig.add_bar(x=cob["mes"], y=cob["personas"], marker_color=col, row=2, col=1, showlegend=False,
                    hovertemplate="%{x}: %{y}<extra></extra>")
        fig.add_hline(y=cob["filas"].median() * cfg.mes_incompleto_frac, line_dash="dot", line_color=F.MUTED, row=1, col=1)
        reg.fig(SEC, "Cobertura por mes", F.estilo(fig, alto=480),
                "Barras grises = meses marcados como incompletos (pocas filas frente a la mediana o rango que no "
                "cubre el mes). La línea punteada es el umbral de filas configurado (fracción de la mediana). "
                "Un mes bajo al principio o al final suele ser un corte del extracto.")

    # Duraciones extremas por zona
    v = validos.assign(min=(validos["fin"] - validos["inicio"]).dt.total_seconds() / 60)
    g = v.groupby("zona", observed=True)["min"]
    ext = pd.DataFrame({"nombre": g.size().index.map(nom), "n": g.size(), "p99_min": g.quantile(0.99), "p999_min": g.quantile(0.999),
                        "max_min": g.max(),
                        "p_mas_24h": g.apply(lambda x: (x > 1440).mean()),
                        "p_mas_7d": g.apply(lambda x: (x > 10080).mean()),
                        "p_mas_30d": g.apply(lambda x: (x > 43200).mean())}).reset_index()
    reg.tabla(SEC, "duraciones_extremas", ext, "Por zona (segmentos crudos): percentiles altos de duración y "
              "proporción de segmentos de más de 24 h, 7 días y 30 días.")
    v["franja"] = pd.cut(v["min"], FRANJAS_MIN, labels=FRANJAS_TXT, right=False)
    h = v.groupby(["zona", "franja"], observed=False).size().rename("n").reset_index()
    h["p"] = h["n"] / h.groupby("zona")["n"].transform("sum")
    fig, grupos = go.Figure(), []
    for z, hz in h.groupby("zona", sort=False):
        fig.add_bar(x=hz["franja"].astype(str), y=hz["p"], marker_color=F.SERIES[0], name=nom(z),
                    hovertemplate="%{x}: %{y:.2%}<extra></extra>", showlegend=False)
        grupos.append((nom(z), 1))
    fig.update_yaxes(tickformat=".0%")
    F.selector(F.estilo(fig, "duración del segmento (franjas en escala log)", "proporción de segmentos"), grupos)
    reg.fig(SEC, "Duración de segmentos crudos por franja", fig,
            "Proporción de segmentos de la zona elegida en cada franja de duración; las franjas crecen de forma "
            "aproximadamente logarítmica. Las colas a la derecha (días) son los valores extremos de la tabla "
            "duraciones_extremas. Es el dato crudo, antes de unir segmentos.")
    return validos, meses_inc
