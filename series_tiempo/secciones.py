"""Secciones del reporte. Cada una recibe las series agregadas y agrega figuras y tablas.
Nada aquí ve pacientes: todo parte de conteos por hora, día o semana."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from Cuellos_botella import figuras as F

from . import calendario
from .datos import Series, tramo_continuo
from .reporte import Registro

HORAS = [f"{h:02d}h" for h in range(24)]
DIAS = F.DIAS
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
C1, C2 = F.SERIES[0], F.SERIES[1]


# --- utilidades ------------------------------------------------------------------------
def dias_ok(s: Series) -> pd.DataFrame:
    """Días completos (sin meses incompletos ni días cortados)."""
    return s.dias[s.dias["completo"]]


def dias_continuos(s: Series) -> pd.DataFrame:
    """El tramo más largo de días completos seguidos (para STL, ACF y pruebas)."""
    return s.dias[tramo_continuo(s.dias["completo"])]


def horas_continuas(s: Series) -> pd.DataFrame:
    return s.horas[tramo_continuo(s.horas["completo"].astype(bool))]


def semanal(df: pd.DataFrame, completo: pd.Series) -> pd.DataFrame:
    """Suma por semana (lunes a domingo, fecha = lunes) solo de semanas con los 7 días completos."""
    ok = completo.reindex(df.index).fillna(False).astype(bool)
    w = df[ok].resample("W-MON", label="left", closed="left").sum()
    n = ok[ok].resample("W-MON", label="left", closed="left").size()
    return w[n.reindex(w.index).fillna(0) == 7]


def _sombra(fig, s: Series, fila=None):
    for m in sorted(s.meses_incompletos):
        kw = dict(row=fila, col=1) if fila else {}
        fig.add_vrect(x0=m.start_time, x1=(m + 1).start_time, fillcolor=F.MUTED, opacity=0.15,
                      line_width=0, layer="below", **kw)


def _incompletos_txt(s: Series) -> str:
    return (" Las franjas grises son meses incompletos, que no entran en ningún cálculo." if s.meses_incompletos
            else "")


# --- A. Datos y cobertura ---------------------------------------------------------------
def cobertura(s: Series, reg: Registro) -> None:
    sec = "A. Datos y cobertura"
    d, ok = s.dias, dias_ok(s)
    hc = s.horas[s.horas["completo"].astype(bool)]
    meses = ", ".join(str(m) for m in sorted(s.meses_incompletos)) or "ninguno"
    res = pd.DataFrame([
        ("primer día", f"{d.index.min():%Y-%m-%d}"), ("último día", f"{d.index.max():%Y-%m-%d}"),
        ("días en total", f"{len(d)}"), ("días completos (entran al análisis)", f"{len(ok)}"),
        ("tramo continuo más largo de días completos", f"{len(dias_continuos(s))}"),
        ("meses incompletos (excluidos)", meses),
        ("llegadas por día: media / mediana", f"{ok['llegadas'].mean():.1f} / {ok['llegadas'].median():.0f}"),
        ("llegadas por hora: media", f"{hc['llegadas'].mean():.2f}"),
        ("horas sin ninguna llegada", f"{(hc['llegadas'] == 0).mean():.1%}"),
    ], columns=["indicador", "valor"])
    reg.tabla(sec, "cobertura", res, "Rango de la serie, qué parte entra al análisis y nivel general.",
              titulo="Resumen de la serie", mostrar=True)

    fig = go.Figure()
    fig.add_scatter(x=d.index, y=d["llegadas"], mode="lines", line=dict(color=F.EJE, width=1), name="por día")
    m7 = d["llegadas"].where(d["completo"]).rolling(7, center=True, min_periods=5).mean()
    m28 = d["llegadas"].where(d["completo"]).rolling(28, center=True, min_periods=20).mean()
    fig.add_scatter(x=d.index, y=m7, mode="lines", line=dict(color=C1, width=1.5), name="media móvil 7 días")
    fig.add_scatter(x=d.index, y=m28, mode="lines", line=dict(color=C2, width=2.5), name="media móvil 28 días")
    _sombra(fig, s)
    fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.06))
    reg.fig(sec, "Llegadas a urgencias por día", F.estilo(fig, None, "llegadas por día", alto=480),
            "Episodios que empiezan en urgencias, contados por día de llegada, con medias móviles de 7 y 28 días."
            + _incompletos_txt(s),
            "La línea gris es el dato crudo; la de 7 días quita el patrón semanal y la de 28 deja ver el nivel. "
            "Usa la barra de abajo para hacer zoom en un periodo.")


# --- B. Nivel y tendencia ---------------------------------------------------------------
def tendencia(s: Series, reg: Registro) -> None:
    sec = "B. Nivel y tendencia"
    ok = dias_ok(s)
    m = ok.groupby([ok.index.year, ok.index.month])["llegadas"].mean()
    fig = go.Figure()
    for i, anio in enumerate(sorted(set(m.index.get_level_values(0)))):
        ma = m.loc[anio].reindex(range(1, 13))
        fig.add_scatter(x=MESES, y=ma.to_numpy(), mode="lines+markers", name=str(anio),
                        line=dict(color=F.SERIES[i % len(F.SERIES)], width=2), marker=dict(size=7))
    reg.fig(sec, "Año sobre año: llegadas por día según el mes", F.estilo(fig, None, "llegadas promedio por día"),
            "Promedio de llegadas por día en cada mes, una línea por año (solo días completos).",
            "Si las líneas se mueven juntas, hay estacionalidad anual; si una queda por encima de otra en todos "
            "los meses, hay tendencia. Con menos de dos años completos, separar las dos cosas no es confiable.")

    c = dias_continuos(s)
    filas = []
    if len(c) > 60:
        t = np.arange(len(c)) / 365.25
        y = c["llegadas"].to_numpy(dtype=float)
        b, a = np.polyfit(t, y, 1)
        pred = a + b * t
        r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
        filas += [("pendiente (llegadas/día por año)", round(b, 2)),
                  ("pendiente como % de la media por año", f"{100 * b / y.mean():.1f} %"),
                  ("R² de la recta (cuánto explica la tendencia sola)", round(r2, 3))]
    anual = ok.groupby(ok.index.year)["llegadas"].agg(["mean", "size"])
    for anio, f in anual.iterrows():
        filas.append((f"{anio}: llegadas/día (días completos)", f"{f['mean']:.1f} ({int(f['size'])} días)"))
    reg.tabla(sec, "tendencia", pd.DataFrame(filas, columns=["indicador", "valor"]),
              "Recta de tendencia sobre el tramo continuo de días completos y promedio por año. Un año con "
              "pocos días completos no es comparable.", titulo="Tendencia", mostrar=True)


# --- C. Dentro del día ------------------------------------------------------------------
def dentro_del_dia(s: Series, reg: Registro) -> None:
    sec = "C. Estacionalidad dentro del día"
    h = s.horas[s.horas["completo"].astype(bool)]
    por = h.groupby(h.index.hour)["llegadas"]
    p = pd.DataFrame({"hora": range(24), "media": por.mean().to_numpy(), "p10": por.quantile(0.1).to_numpy(),
                      "p50": por.median().to_numpy(), "p90": por.quantile(0.9).to_numpy(),
                      "varianza": por.var().to_numpy()})
    p["varianza_sobre_media"] = p["varianza"] / p["media"]
    reg.tabla(sec, "perfil_hora", p, "Llegadas por hora del día: media, percentiles y varianza/media (días completos).")
    fig = go.Figure()
    fig.add_scatter(x=HORAS, y=p["p90"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=HORAS, y=p["p10"], mode="lines", line=dict(width=0), fill="tonexty",
                    fillcolor="rgba(42,120,214,0.15)", name="p10 a p90")
    fig.add_scatter(x=HORAS, y=p["media"], mode="lines+markers", line=dict(color=C1, width=2.5), name="media")
    pico, valle = p["media"].idxmax(), p["media"].idxmin()
    reg.fig(sec, "Llegadas según la hora del día", F.estilo(fig, "hora de llegada", "llegadas en la hora"),
            "Promedio de llegadas en cada hora del día y la banda donde cae el 80 % de las horas.",
            f"La hora pico es {HORAS[pico]} y la más tranquila {HORAS[valle]}; la pico tiene "
            f"{p['media'][pico] / max(p['media'][valle], 1e-9):.1f} veces más llegadas. Una banda ancha = horas "
            "muy variables.")

    t = h.groupby([h.index.dayofweek, h.index.hour])["llegadas"].mean().unstack().reindex(index=range(7), columns=range(24))
    fig = go.Figure()
    for i in range(7):
        fig.add_scatter(x=HORAS, y=t.loc[i].to_numpy(), mode="lines", name=DIAS[i],
                        line=dict(color=F.SERIES[i % len(F.SERIES)], width=2 if i in (0, 5, 6) else 1.2))
    reg.fig(sec, "Perfil del día para cada día de la semana", F.estilo(fig, "hora de llegada", "llegadas promedio"),
            "Las 24 horas de cada día de la semana, una línea por día.",
            "Si las líneas tienen la misma forma y solo cambian de altura, el patrón diario y el semanal se "
            "suman. Si la forma cambia (p. ej. el sábado el pico llega más tarde), interactúan.")

    fig = go.Figure(F.heatmap_dia_hora(t.to_numpy(), HORAS, "llegadas"))
    reg.fig(sec, "Mapa de calor día × hora", F.estilo(fig, "hora de llegada", None),
            "Promedio de llegadas para cada combinación de día de la semana y hora (días completos).",
            "Celdas oscuras = franjas con más llegadas. Es la vista más rápida para ver dónde se concentra la demanda.")


# --- D. Semana ---------------------------------------------------------------------------
def semana(s: Series, reg: Registro) -> None:
    sec = "D. Estacionalidad semanal"
    ok = dias_ok(s)
    ok = ok[~ok["especial"]] if "especial" in ok else ok
    fig = go.Figure()
    for i in range(7):
        v = ok.loc[ok["dia_semana"] == i, "llegadas"]
        fig.add_box(y=v, name=DIAS[i], marker_color=C1, boxpoints=False, line_width=1.5, showlegend=False)
    media = ok["llegadas"].mean()
    t = ok.groupby("dia_semana")["llegadas"].agg(["mean", "median", "std", "size"]).reindex(range(7)).reset_index()
    t["dia"] = [DIAS[i] for i in t["dia_semana"]]
    t["veces_la_media"] = t["mean"] / media
    reg.tabla(sec, "dia_semana", t, "Llegadas por día según el día de la semana (sin festivos ni temporadas).")
    reg.fig(sec, "Llegadas por día según el día de la semana", F.estilo(fig, None, "llegadas por día"),
            "Distribución de las llegadas diarias para cada día de la semana, sin festivos ni temporadas especiales.",
            f"El día más cargado es {DIAS[int(t['mean'].idxmax())]} ({t['veces_la_media'].max():.2f} veces la media) "
            f"y el más liviano {DIAS[int(t['mean'].idxmin())]} ({t['veces_la_media'].min():.2f}). Cajas que no se "
            "solapan = diferencia clara.")


# --- E. Año -------------------------------------------------------------------------------
def anio(s: Series, reg: Registro) -> None:
    sec = "E. Estacionalidad anual"
    ok = dias_ok(s)
    fig = go.Figure()
    for m in range(1, 13):
        v = ok.loc[ok.index.month == m, "llegadas"]
        if len(v):
            fig.add_box(y=v, name=MESES[m - 1], marker_color=C2, boxpoints=False, line_width=1.5, showlegend=False)
    t = ok.groupby(ok.index.month)["llegadas"].agg(["mean", "size"]).reindex(range(1, 13)).reset_index()
    t.columns = ["mes", "media", "dias"]
    t["veces_la_media"] = t["media"] / ok["llegadas"].mean()
    reg.tabla(sec, "mes", t, "Llegadas por día según el mes (todos los años juntos, días completos).")
    anios = ok.index.year.nunique()
    reg.fig(sec, "Llegadas por día según el mes", F.estilo(fig, None, "llegadas por día"),
            f"Llegadas diarias agrupadas por mes del año, juntando los {anios} años disponibles.",
            "Meses con la caja más alta concentran demanda. Con pocos años, un mes puede verse alto por un "
            "solo año atípico: compáralo con 'Año sobre año' en la sección B.")

    w = ok.groupby("semana_anio")["llegadas"].mean() if "semana_anio" in ok else pd.Series(dtype=float)
    fig = go.Figure(go.Scatter(x=w.index, y=w.to_numpy(), mode="lines+markers", line=dict(color=C2, width=2),
                               marker=dict(size=5)))
    reg.fig(sec, "Llegadas por día según la semana del año", F.estilo(fig, "semana del año (ISO)", "llegadas por día"),
            "Promedio de llegadas diarias por semana del año, juntando todos los años.",
            "Muestra picos de pocas semanas que el promedio por mes esconde (Semana Santa, Carnaval, fin de año).")


# --- F. Calendario -------------------------------------------------------------------------
def calendario_efectos(s: Series, reg: Registro) -> None:
    sec = "F. Festivos y temporadas"
    ok = dias_ok(s).copy()
    if "especial" not in ok:
        return
    normales = ok[~ok["especial"] & ~ok["despues_de_festivo"]]
    base = normales.groupby(["anio", "mes", "dia_semana"])["llegadas"].mean()
    clave = list(zip(ok["anio"], ok["mes"], ok["dia_semana"]))
    ok["esperado"] = base.reindex(clave).to_numpy()
    ok["razon"] = ok["llegadas"] / ok["esperado"]
    filas = []
    for col, nombre in calendario.CATEGORIAS.items():
        r = ok.loc[ok[col] & ok["razon"].notna(), "razon"]
        filas.append({"categoria": nombre, "dias": len(r), "razon_mediana": r.median() if len(r) else np.nan,
                      "p25": r.quantile(0.25) if len(r) else np.nan, "p75": r.quantile(0.75) if len(r) else np.nan})
    t = pd.DataFrame(filas)
    reg.tabla(sec, "efecto_calendario", t, "Llegadas del día ÷ lo esperado para ese mes y día de la semana en días "
              "normales. 1 = igual que un día normal; 0.8 = 20 % menos.", titulo="Efecto de festivos y temporadas",
              mostrar=True)
    tt = t.dropna(subset=["razon_mediana"])
    fig = go.Figure(go.Bar(x=tt["categoria"], y=tt["razon_mediana"], marker_color=C1,
                           error_y=dict(type="data", symmetric=False, array=tt["p75"] - tt["razon_mediana"],
                                        arrayminus=tt["razon_mediana"] - tt["p25"], color=F.MUTED),
                           customdata=tt["dias"], hovertemplate="%{x}: %{y:.2f} (%{customdata} días)<extra></extra>"))
    fig.add_hline(y=1, line_dash="dash", line_color=F.MUTED)
    reg.fig(sec, "Llegadas en días especiales frente a un día normal", F.estilo(fig, None, "llegadas ÷ esperado"),
            "Para cada tipo de día especial, cuántas llegadas hubo frente a un día normal del mismo mes y día de "
            "la semana (mediana y rango intercuartil).",
            "Barras por debajo de la línea = menos llegadas que un día normal; por encima = más. Con pocos días "
            "en una categoría (mira el número al pasar el cursor), el efecto es poco confiable.")

    fest = ok.index[ok["festivo"]]
    filas = []
    for k in range(-3, 4):
        r = ok["razon"].reindex(fest + pd.Timedelta(days=k)).dropna()
        filas.append({"desfase": k, "razon_media": r.mean() if len(r) else np.nan, "dias": len(r)})
    a = pd.DataFrame(filas)
    fig = go.Figure(go.Scatter(x=a["desfase"], y=a["razon_media"], mode="lines+markers",
                               line=dict(color=C2, width=2.5), marker=dict(size=9)))
    fig.add_hline(y=1, line_dash="dash", line_color=F.MUTED)
    fig.update_xaxes(tickvals=list(range(-3, 4)), ticktext=["-3", "-2", "-1", "festivo", "+1", "+2", "+3"])
    reg.fig(sec, "Alrededor de un festivo", F.estilo(fig, "días respecto al festivo", "llegadas ÷ esperado"),
            "Llegadas en los días antes y después de un festivo frente a un día normal.",
            "Si el día siguiente sube por encima de 1, la gente que no fue en el festivo llega después "
            "(demanda represada).")


# --- G. Descomposición ------------------------------------------------------------------------
def _fuerza(resid, comp) -> float:
    """Fuerza de un componente (Hyndman): 1 − Var(resto)/Var(componente + resto), entre 0 y 1."""
    v = np.nanvar(resid + comp)
    return float(max(0.0, 1 - np.nanvar(resid) / v)) if v > 0 else np.nan


def descomposicion(s: Series, reg: Registro) -> None:
    from statsmodels.tsa.seasonal import MSTL, STL
    sec = "G. Descomposición"
    c = dias_continuos(s)["llegadas"].astype(float)
    filas = []
    if len(c) >= 28:
        periodos = (7, 365) if len(c) >= 2 * 365 + 30 else (7,)
        if len(periodos) == 2:
            r = MSTL(c, periods=periodos).fit()
            est = r.seasonal
            comps = [("tendencia", r.trend), ("semanal (7)", est.iloc[:, 0]), ("anual (365)", est.iloc[:, 1]),
                     ("resto", r.resid)]
        else:
            r = STL(c, period=7, robust=True).fit()
            comps = [("tendencia", r.trend), ("semanal (7)", r.seasonal), ("resto", r.resid)]
            reg.avisos.append("Hay menos de dos años seguidos de días completos: la descomposición diaria no "
                              "separa estacionalidad anual (queda mezclada con la tendencia).")
        fig = make_subplots(rows=len(comps) + 1, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                            subplot_titles=["observado"] + [n for n, _ in comps])
        fig.add_scatter(x=c.index, y=c, mode="lines", line=dict(color=F.TINTA_2, width=1), row=1, col=1, showlegend=False)
        for i, (n, v) in enumerate(comps):
            fig.add_scatter(x=v.index, y=v, mode="lines", line=dict(color=F.SERIES[i % len(F.SERIES)], width=1.3),
                            row=i + 2, col=1, showlegend=False)
        fig.update_layout(margin=dict(b=40))
        reg.fig(sec, "Descomposición de la serie diaria", F.estilo(fig, alto=170 * (len(comps) + 1)),
                "La serie diaria separada en tendencia, estacionalidad (semanal y, si hay dos años, anual) y resto "
                "(STL/MSTL sobre el tramo continuo de días completos).",
                "Compara la amplitud de cada panel: el componente que más se mueve es el que más explica. El resto "
                "debería verse como ruido sin patrón; picos sueltos ahí son días atípicos.")
        resid = comps[-1][1].to_numpy()
        for n, v in comps[:-1]:
            filas.append({"serie": "diaria", "componente": n, "fuerza": _fuerza(resid, v.to_numpy())})
        z = (comps[-1][1] - comps[-1][1].mean()) / comps[-1][1].std()
        atip = z[np.abs(z) > 3]
        reg.tabla(sec, "dias_atipicos", pd.DataFrame({"fecha": atip.index.strftime("%Y-%m-%d"),
                                                       "z_resto": atip.round(2).to_numpy()}),
                  "Días con resto de la descomposición a más de 3 desviaciones estándar (candidatos a atípicos).",
                  titulo="Días atípicos", mostrar=len(atip) > 0)

    hc = horas_continuas(s)["llegadas"].astype(float)
    hc = hc[hc.index > hc.index.max() - pd.Timedelta(weeks=52)] if len(hc) else hc   # último año: basta y es rápido
    if len(hc) >= 3 * 168:
        r = MSTL(hc, periods=(24, 168)).fit()
        est = r.seasonal
        comps = [("tendencia", r.trend), ("diaria (24 h)", est.iloc[:, 0]), ("semanal (168 h)", est.iloc[:, 1]),
                 ("resto", r.resid)]
        ult = hc.index >= hc.index.max() - pd.Timedelta(weeks=6)
        fig = make_subplots(rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                            subplot_titles=["observado (últimas 6 semanas)"] + [n for n, _ in comps])
        fig.add_scatter(x=hc.index[ult], y=hc[ult], mode="lines", line=dict(color=F.TINTA_2, width=1), row=1, col=1,
                        showlegend=False)
        for i, (n, v) in enumerate(comps):
            fig.add_scatter(x=v.index[ult], y=v[ult], mode="lines", line=dict(color=F.SERIES[i % len(F.SERIES)], width=1.2),
                            row=i + 2, col=1, showlegend=False)
        reg.fig(sec, "Descomposición de la serie horaria", F.estilo(fig, alto=850),
                "La serie por hora separada en tendencia, ciclo diario (24 h), ciclo semanal (168 h) y resto "
                "(MSTL sobre el último año del tramo continuo; se muestran las últimas 6 semanas para ver el detalle).",
                "El ciclo de 168 h recoge lo que el de 24 h no explica: diferencias entre días de la semana y entre "
                "sus perfiles horarios.")
        resid = r.resid.to_numpy()
        for n, v in comps[:-1]:
            filas.append({"serie": "horaria", "componente": n, "fuerza": _fuerza(resid, v.to_numpy())})
    if filas:
        reg.tabla(sec, "fuerza_componentes", pd.DataFrame(filas),
                  "Fuerza de cada componente (0 = no aporta, 1 = explica casi todo frente al resto). Por encima de "
                  "~0.6 se considera fuerte.", titulo="Fuerza de cada componente", mostrar=True)


# --- H. Autocorrelación -----------------------------------------------------------------------
def _acf_fig(valores: pd.Series, lags: int, marcas: list[int], titulo_x: str, pacf: bool = False) -> go.Figure:
    from statsmodels.tsa.stattools import acf
    from statsmodels.tsa.stattools import pacf as fpacf
    v = valores.dropna().to_numpy(dtype=float)
    lags = min(lags, len(v) // 2 - 1)
    a = fpacf(v, nlags=lags, method="ywm") if pacf else acf(v, nlags=lags, fft=True)
    banda = 1.96 / np.sqrt(len(v))
    colores = [C2 if k in marcas else C1 for k in range(len(a))]
    fig = go.Figure(go.Bar(x=list(range(len(a))), y=a, marker_color=colores, width=0.6,
                           hovertemplate="rezago %{x}: %{y:.2f}<extra></extra>"))
    for y in (banda, -banda):
        fig.add_hline(y=y, line_dash="dot", line_color=F.MUTED)
    return F.estilo(fig, titulo_x, "PACF" if pacf else "ACF")


def autocorrelacion(s: Series, reg: Registro) -> None:
    sec = "H. Autocorrelación"
    c = dias_continuos(s)["llegadas"].astype(float)
    if len(c) >= 30:
        reg.fig(sec, "ACF de la serie diaria", _acf_fig(c, 56, [7, 14, 21, 28, 35, 42, 49, 56], "rezago (días)"),
                "Correlación de las llegadas de un día con las de k días antes (barras naranja: múltiplos de 7).",
                "Barras que salen de la banda punteada son correlaciones reales. Picos cada 7 días = ciclo semanal. "
                "Barras que bajan muy despacio = tendencia o nivel que cambia (serie no estacionaria).")
        reg.fig(sec, "PACF de la serie diaria", _acf_fig(c, 35, [7, 14, 21, 28, 35], "rezago (días)", pacf=True),
                "Correlación parcial: cuánto aporta el rezago k una vez descontados los rezagos más cortos.",
                "El último rezago corto que sale de la banda sugiere el orden autorregresivo; picos en 7, 14 sugieren "
                "términos autorregresivos estacionales.")
        d7 = c.diff(7)
        reg.fig(sec, "ACF después de quitar el ciclo semanal (diferencia de 7 días)",
                _acf_fig(d7, 56, [7, 14, 21, 28], "rezago (días)"),
                "La misma ACF sobre y(t) − y(t−7), es decir, quitando el patrón semanal.",
                "Si casi todo queda dentro de la banda, la diferencia semanal ya volvió la serie casi ruido; un "
                "pico negativo en 7 es típico de esta diferencia y se corrige con un término MA estacional.")
    hc = horas_continuas(s)["llegadas"].astype(float)
    if len(hc) >= 2 * 168:
        reg.fig(sec, "ACF de la serie horaria", _acf_fig(hc, 24 * 15, [24 * k for k in range(1, 16)], "rezago (horas)"),
                "Correlación de las llegadas de una hora con las de k horas antes, hasta 15 días (naranja: múltiplos "
                "de 24 h).",
                "Picos cada 24 h = ciclo diario; el pico en 168 h más alto que los vecinos = ciclo semanal.")
    if len(c) >= 60:
        from statsmodels.stats.diagnostic import acorr_ljungbox
        from statsmodels.tsa.seasonal import STL
        resto = STL(c, period=7, robust=True).fit().resid
        lb = acorr_ljungbox(resto, lags=[7, 14, 28], return_df=True).reset_index()
        lb.columns = ["rezagos", "estadistico", "p_valor"]
        reg.tabla(sec, "ljung_box_resto", lb,
                  "Prueba de Ljung-Box sobre el resto de la descomposición STL semanal. p < 0.05 = el resto todavía "
                  "tiene autocorrelación.",
                  titulo="¿Queda autocorrelación después de quitar tendencia y ciclo semanal?", mostrar=True)


# --- I. Estacionariedad ------------------------------------------------------------------------
def estacionariedad(s: Series, reg: Registro) -> None:
    import warnings

    from statsmodels.tsa.stattools import adfuller, kpss
    sec = "I. Estacionariedad"
    c = dias_continuos(s)["llegadas"].astype(float)
    if len(c) < 60:
        return
    filas = []
    for nombre, v in (("nivel", c), ("diferencia 1 día", c.diff()), ("diferencia 7 días", c.diff(7)),
                      ("diferencia 1 y 7 días", c.diff(7).diff())):
        v = v.dropna()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            p_adf = adfuller(v, autolag="AIC")[1]
            p_kpss = kpss(v, regression="c", nlags="auto")[1]
        lectura = ("estacionaria" if p_adf < 0.05 and p_kpss > 0.05 else
                   "no estacionaria" if p_adf >= 0.05 and p_kpss <= 0.05 else "dudosa (las pruebas no coinciden)")
        filas.append({"serie": nombre, "p_ADF": p_adf, "p_KPSS": p_kpss, "lectura": lectura})
    reg.tabla(sec, "pruebas_estacionariedad", pd.DataFrame(filas),
              "ADF: hipótesis nula = hay raíz unitaria (no estacionaria); p < 0.05 la rechaza. KPSS: hipótesis nula = "
              "estacionaria; p < 0.05 la rechaza (el KPSS de statsmodels topa el p entre 0.01 y 0.1).",
              titulo="Pruebas ADF y KPSS (serie diaria)", mostrar=True)
    r_m = c.rolling(28).mean()
    r_s = c.rolling(28).std()
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, subplot_titles=("media móvil 28 días", "desviación móvil 28 días"))
    fig.add_scatter(x=c.index, y=r_m, mode="lines", line=dict(color=C1, width=2), row=1, col=1, showlegend=False)
    fig.add_scatter(x=c.index, y=r_s, mode="lines", line=dict(color=C2, width=2), row=2, col=1, showlegend=False)
    reg.fig(sec, "Media y variabilidad en el tiempo", F.estilo(fig, alto=480),
            "Media y desviación estándar de las llegadas diarias en ventanas móviles de 28 días.",
            "Una media que sube o baja = tendencia. Una desviación que crece cuando crece la media = la "
            "variabilidad depende del nivel.")


# --- J. Distribución -----------------------------------------------------------------------------
def distribucion(s: Series, reg: Registro) -> None:
    from scipy import stats
    sec = "J. Distribución de los conteos"
    h = s.horas[s.horas["completo"].astype(bool)]
    y = h["llegadas"].to_numpy()
    if y.size == 0:
        return
    k = np.arange(0, int(np.quantile(y, 0.999)) + 2)
    obs = np.bincount(y, minlength=k.size)[: k.size] / y.size
    poi = stats.poisson.pmf(k, y.mean())
    fig = go.Figure()
    fig.add_bar(x=k, y=obs, marker_color=C1, name="observado")
    fig.add_scatter(x=k, y=poi, mode="lines+markers", line=dict(color=C2, width=2), name="Poisson con la misma media")
    fig.update_yaxes(tickformat=".0%")
    reg.fig(sec, "Llegadas por hora frente a una Poisson", F.estilo(fig, "llegadas en la hora", "proporción de horas"),
            "Cuántas horas tuvieron 0, 1, 2… llegadas, contra lo que daría una Poisson con la misma media.",
            "Si las barras son más anchas que la curva (más horas con muy pocas y con muchas), hay sobredispersión. "
            "Ojo: parte se debe al ciclo del día; la figura siguiente lo descuenta.")

    g = h.groupby([h.index.dayofweek, h.index.hour])["llegadas"].agg(["mean", "var"])
    fig = go.Figure()
    fig.add_scatter(x=g["mean"], y=g["var"], mode="markers", marker=dict(color=C1, size=7, opacity=0.8),
                    name="franja día×hora", hovertemplate="media %{x:.2f} · varianza %{y:.2f}<extra></extra>")
    mx = float(max(g["mean"].max(), g["var"].max())) * 1.05
    fig.add_scatter(x=[0, mx], y=[0, mx], mode="lines", line=dict(color=F.MUTED, dash="dash"), name="varianza = media (Poisson)")
    disp = float((g["var"] / g["mean"]).replace([np.inf, -np.inf], np.nan).mean())
    reg.fig(sec, "Varianza frente a media en cada franja", F.estilo(fig, "media de llegadas en la franja", "varianza"),
            "Cada punto es una franja día×hora (168): su media y su varianza de llegadas por hora.",
            f"En una Poisson los puntos caerían sobre la diagonal. En promedio la varianza es {disp:.2f} veces la "
            "media: por encima de 1 = sobredispersión aun descontando el ciclo.")

    d = dias_ok(s)["llegadas"].astype(float)
    filas = [("varianza/media por franja día×hora (promedio)", round(disp, 3)),
             ("horas con 0 llegadas: observado", f"{(y == 0).mean():.1%}"),
             ("horas con 0 llegadas: esperado por Poisson por franja",
              f"{np.mean(np.exp(-g['mean'].to_numpy())):.1%}")]
    if len(d) > 30 and (d > 0).all():
        _, lam = stats.boxcox(d.to_numpy())
        filas.append(("lambda de Box-Cox de las llegadas diarias", round(float(lam), 2)))
        filas.append(("lectura de lambda", "≈1 sin transformar · ≈0.5 raíz · ≈0 logaritmo"))
    reg.tabla(sec, "dispersion", pd.DataFrame(filas, columns=["indicador", "valor"]),
              "Sobredispersión, exceso de ceros y transformación sugerida para la serie diaria.",
              titulo="Dispersión y transformación", mostrar=True)


# --- K. Otras series del flujo ---------------------------------------------------------------------
def flujo(s: Series, reg: Registro) -> None:
    sec = "K. Otras series del flujo"
    d = s.dias
    w = d[["llegadas", "llegadas_hospitalizan", "llegadas_contacto_breve", "ingresos_cama", "altas_cama"]]
    w = semanal(w, d["completo"])
    nombres = {"llegadas": "llegadas a urgencias", "llegadas_hospitalizan": "llegadas que terminan en cama",
               "llegadas_contacto_breve": "contactos breves (< 15 min)", "ingresos_cama": "ingresos a cama",
               "altas_cama": "altas de cama"}
    fig = go.Figure()
    for i, (c, n) in enumerate(nombres.items()):
        fig.add_scatter(x=w.index, y=w[c], mode="lines", name=n, line=dict(color=F.SERIES[i], width=2))
    reg.fig(sec, "Series semanales del flujo", F.estilo(fig, None, "eventos por semana", alto=460),
            "Totales por semana (semanas de días completos) de llegadas, llegadas que terminan en cama, contactos "
            "breves, ingresos a cama (de cualquier origen) y altas de cama.",
            "Ingresos y altas deberían moverse juntos a largo plazo; si los ingresos superan a las altas por "
            "varias semanas, el censo de camas sube.")

    h = s.horas[s.horas["completo"].astype(bool)]
    p = h.groupby(h.index.hour)[["llegadas_hospitalizan", "ingresos_cama", "altas_cama"]].mean()
    fig = go.Figure()
    for i, (c, n) in enumerate((("llegadas_hospitalizan", "llegadas que terminan en cama"),
                                ("ingresos_cama", "ingresos a cama"), ("altas_cama", "altas de cama"))):
        fig.add_scatter(x=HORAS, y=p[c], mode="lines+markers", name=n, line=dict(color=F.SERIES[i + 1], width=2))
    reg.fig(sec, "¿A qué hora se liberan y se ocupan las camas?", F.estilo(fig, "hora del día", "eventos promedio en la hora"),
            "Promedio por hora del día de las llegadas que acaban hospitalizadas, los ingresos a cama y las altas.",
            "Si las altas se concentran tarde y las llegadas que necesitan cama temprano, los pacientes esperan en "
            "urgencias el desfase entre las dos curvas.")

    cen = d.loc[d["completo"], ["censo_urgencias_medio", "censo_hospitalizacion_medio"]]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, subplot_titles=("urgencias", "hospitalización"))
    fig.add_scatter(x=cen.index, y=cen.iloc[:, 0], mode="lines", line=dict(color=C1, width=1.2), row=1, col=1, showlegend=False)
    fig.add_scatter(x=cen.index, y=cen.iloc[:, 1], mode="lines", line=dict(color=C2, width=1.2), row=2, col=1, showlegend=False)
    reg.fig(sec, "Censo medio diario", F.estilo(fig, alto=480),
            "Personas presentes en promedio cada día (como la consulta 25: urgencias cortado al ingreso a cama, "
            "sin estancias extremas).",
            "La ocupación absoluta todavía no es confiable (capacidad real pendiente con el HUN); mira los "
            "patrones y los cambios de nivel.")

    hc = horas_continuas(s)
    if len(hc) >= 2 * 168:
        def sin_ciclo(x):
            return x - x.groupby([x.index.dayofweek, x.index.hour]).transform("mean")
        filas = []
        pares = (("llegadas", "censo_urgencias", "llegadas → censo de urgencias"),
                 ("altas_cama", "ingresos_desde_urgencias", "altas de cama → ingresos desde urgencias"))
        for a, b, n in pares:
            xa, xb = sin_ciclo(hc[a].astype(float)), sin_ciclo(hc[b].astype(float))
            for k in range(0, 25):
                filas.append({"par": n, "desfase_h": k, "correlacion": xa.corr(xb.shift(-k))})
        cc = pd.DataFrame(filas)
        fig = go.Figure()
        for i, (_, _, n) in enumerate(pares):
            cz = cc[cc["par"] == n]
            fig.add_scatter(x=cz["desfase_h"], y=cz["correlacion"], mode="lines+markers", name=n,
                            line=dict(color=F.SERIES[i], width=2))
        reg.tabla(sec, "correlacion_cruzada", cc, "Correlación entre una serie y otra k horas después, sin el ciclo día×hora.")
        reg.fig(sec, "¿Cuánto tarda una serie en mover a la otra?", F.estilo(fig, "horas después", "correlación (sin ciclo día×hora)"),
                "Correlación entre una serie en la hora t y otra en la hora t+k, después de quitar a las dos su "
                "promedio por día y hora (así no se correlacionan solo por tener el mismo horario).",
                "Un pico en k horas = la primera serie anticipa a la segunda por k horas. P. ej., si las altas de "
                "cama anticipan los ingresos desde urgencias, la cama es el cuello de botella.")

    m = d[d["completo"]].resample("MS")[["llegadas", "llegadas_hospitalizan", "llegadas_contacto_breve"]].sum()
    m["proporcion_hospitalizada"] = m["llegadas_hospitalizan"] / m["llegadas"]
    m["proporcion_contacto_breve"] = m["llegadas_contacto_breve"] / m["llegadas"]
    reg.tabla(sec, "proporciones_mensuales", m.reset_index()[["fecha", "proporcion_hospitalizada", "proporcion_contacto_breve"]],
              "Por mes completo: qué parte de las llegadas termina en cama y qué parte son contactos breves.")


# --- L. Por grupo ------------------------------------------------------------------------------------
def grupos(s: Series, reg: Registro) -> None:
    sec = "L. Por grupo"
    g = s.grupos
    if not isinstance(g.columns, pd.MultiIndex) or g.empty:
        return
    w = semanal(g, s.dias["completo"])
    g = g[s.dias["completo"].reindex(g.index).fillna(False).to_numpy()]
    fig, botones, filas = go.Figure(), [], []
    dims = [x for x in ("edad", "sexo", "destino") if x in g.columns.get_level_values(0)]
    total = 0
    for dim in dims:
        sub = w[dim]
        n = len(sub.columns)
        for i, c in enumerate(sub.columns):
            fig.add_scatter(x=sub.index, y=sub[c], mode="lines", name=str(c), visible=dim == dims[0],
                            line=dict(color=F.SERIES[i % len(F.SERIES)], width=2))
            dd = g[dim][c]
            filas.append({"dimension": dim, "grupo": c, "llegadas_por_dia": dd.mean(),
                          "proporcion": dd.sum() / g[dim].to_numpy().sum(), "cv_diario": dd.std() / dd.mean()
                          if dd.mean() > 0 else np.nan})
        botones.append((dim, total, n))
        total += n
    fig.update_layout(updatemenus=[dict(buttons=[dict(label=f"por {dim}", method="update",
                                                      args=[{"visible": [ini <= j < ini + n for j in range(total)]}])
                                                 for dim, ini, n in botones],
                                        direction="down", x=1, xanchor="right", y=1.0, yanchor="bottom",
                                        bgcolor="#ffffff", bordercolor=F.EJE)], margin=dict(t=90))
    reg.fig(sec, "Llegadas semanales por grupo", F.estilo(fig, None, "llegadas por semana", alto=460),
            "Llegadas por semana separadas por grupo de edad, sexo o destino (menú arriba a la derecha).",
            "Grupos con tendencias o estacionalidades distintas (p. ej. niños con picos en temporada de lluvias) "
            "no se ven en la serie total.")
    reg.tabla(sec, "grupos", pd.DataFrame(filas), "Por grupo: llegadas promedio por día, proporción del total y "
              "coeficiente de variación diario (más alto = más ruidoso).", titulo="Peso y variabilidad de cada grupo",
              mostrar=True)

    if "edad" in dims:
        e = g["edad"]
        dw = e.groupby(e.index.dayofweek).mean()
        dw = dw / dw.mean()
        fig = go.Figure()
        for i, c in enumerate(dw.columns):
            fig.add_scatter(x=DIAS, y=dw[c], mode="lines+markers", name=str(c), line=dict(color=F.SERIES[i % len(F.SERIES)], width=2))
        reg.fig(sec, "Patrón semanal por grupo de edad", F.estilo(fig, None, "llegadas ÷ promedio del grupo"),
                "Para cada grupo de edad, las llegadas de cada día de la semana divididas por el promedio del grupo.",
                "Líneas con formas distintas = cada grupo tiene su propio ciclo semanal.")


# --- M. Tiempos ---------------------------------------------------------------------------------------
def tiempos(s: Series, reg: Registro) -> None:
    sec = "M. Tiempos en urgencias"
    t = s.semanas
    if t is None or t.empty:
        return
    t = t[t["completo"]] if "completo" in t else t
    fig = go.Figure()
    for i, dest in enumerate(sorted(t["destino"].unique())):
        tz = t[t["destino"] == dest]
        col = F.SERIES[i]
        fig.add_scatter(x=tz["semana"], y=tz["p50_h_urg"], mode="lines", name=f"{dest} · sin recorte",
                        line=dict(color=col, width=1.2, dash="dot"))
        fig.add_scatter(x=tz["semana"], y=tz["p50_h_urg_recortado"], mode="lines", name=f"{dest} · con recorte",
                        line=dict(color=col, width=2.2))
    reg.fig(sec, "Mediana de horas en urgencias por semana", F.estilo(fig, None, "horas en urgencias (mediana)", alto=440),
            "Mediana semanal del tiempo en urgencias por destino, con y sin cortar urgencias al ingreso a cama "
            "(solo semanas con 10 episodios o más).",
            "La distancia entre la línea punteada y la continua de 'hospitalizado' es el tiempo que urgencias "
            "seguía abierto con el paciente ya en cama. La continua es la comparable entre destinos.")
    w = semanal(s.dias[["llegadas"]], s.dias["completo"])["llegadas"]
    m = t.merge(w.rename("llegadas_semana").reset_index().rename(columns={"fecha": "semana"}), on="semana")
    filas = []
    fig = go.Figure()
    for i, dest in enumerate(sorted(m["destino"].unique())):
        mz = m[m["destino"] == dest]
        fig.add_scatter(x=mz["llegadas_semana"], y=mz["p50_h_urg_recortado"], mode="markers", name=dest,
                        marker=dict(color=F.SERIES[i], size=8, opacity=0.75))
        if len(mz) > 5:
            filas.append({"destino": dest, "spearman_llegadas_vs_mediana": mz["llegadas_semana"].corr(
                mz["p50_h_urg_recortado"], method="spearman"), "semanas": len(mz)})
    reg.fig(sec, "¿Más llegadas, más espera?", F.estilo(fig, "llegadas en la semana", "mediana de horas en urgencias (con recorte)"),
            "Cada punto es una semana: cuántas llegadas hubo y la mediana del tiempo en urgencias.",
            "Una nube que sube hacia la derecha = cuando llega más gente, cada uno espera más (congestión).")
    if filas:
        reg.tabla(sec, "congestion", pd.DataFrame(filas), "Correlación de Spearman entre llegadas semanales y mediana de "
                  "horas en urgencias (con recorte). Cerca de 0 = sin relación; cerca de 1 = más llegadas, más espera.",
                  titulo="Llegadas y espera", mostrar=True)


SECCIONES = [("cobertura", cobertura), ("tendencia", tendencia), ("dentro del día", dentro_del_dia),
             ("semana", semana), ("año", anio), ("calendario", calendario_efectos),
             ("descomposición", descomposicion), ("autocorrelación", autocorrelacion),
             ("estacionariedad", estacionariedad), ("distribución", distribucion), ("flujo", flujo),
             ("grupos", grupos), ("tiempos", tiempos)]
