"""Semáforo de saturación por turno: convierte el pronóstico horario en alertas accionables.

Idea
----
Para cada turno de los próximos días (mañana 7-13 h, tarde 13-19 h, noche 19-7 h) se calcula la
probabilidad de que la demanda supere lo que históricamente es un turno CARGADO (percentil 75 del
mismo turno) o CRÍTICO (percentil 90), y se asigna un color:

    ROJO      P(turno crítico) >= 40 %                       → protocolo de saturación
    AMARILLO  P(turno crítico) >= 20 % o P(cargado) >= 50 %    → protocolo preventivo
    VERDE     en otro caso                                     → operación normal

Las reglas son de RIESGO RELATIVO y se fijaron antes de ver los datos reales: por definición un turno
cualquiera es crítico el 10 % de las veces y cargado el 25 %. Amarillo = el doble del riesgo normal;
rojo = cuatro veces. Así no se ajustan a mano para que la validación salga bonita.

Rigor
-----
- Umbrales: percentiles por turno de las últimas 52 semanas válidas ANTES del periodo evaluado (la
  demanda tiene tendencia; umbrales de años viejos no describen la operación actual).
- Incertidumbre: la suma de un turno se modela como binomial negativa con la media pronosticada y una
  dispersión estimada con los ERRORES DEL BACKTEST a nivel de turno (fuera de muestra). En la
  validación se usa dejar-una-semana-fuera, así la semana evaluada no calibra su propio intervalo.
- Validación: se aplica el semáforo a las 12 semanas del backtest (pronósticos hechos sin ver esas
  semanas) y se compara el color con lo que pasó. El mismo procedimiento con la naïve sirve de
  referencia: si el semáforo del modelo no anticipa mejor que el de la naïve, no aporta.

Todo trabaja con conteos agregados por turno; nunca con pacientes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

TURNOS = {"mañana": range(7, 13), "tarde": range(13, 19), "noche": [19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6]}
ORDEN_TURNOS = ["mañana", "tarde", "noche"]
HORAS_TURNO = {t: len(list(h)) for t, h in TURNOS.items()}
P_CARGADO, P_CRITICO = 0.75, 0.90         # percentiles históricos que definen turno cargado / crítico
UMBRAL_ROJO = 0.40                        # P(crítico) para rojo: 4 × el riesgo base (10 %)
UMBRAL_AMARILLO_CRITICO = 0.20            # P(crítico) para amarillo: 2 × el riesgo base
UMBRAL_AMARILLO_CARGADO = 0.50            # o P(cargado) para amarillo: 2 × el riesgo base (25 %)
SEMANAS_REFERENCIA = 52
COLORES = ["verde", "amarillo", "rojo"]
CATEGORIAS = ["normal", "cargado", "crítico"]


# --- turnos ----------------------------------------------------------------------------------
def turno_de(horas: pd.DatetimeIndex) -> tuple[pd.DatetimeIndex, np.ndarray]:
    """Fecha del turno y nombre del turno de cada hora. La noche 19-7 h pertenece al día en que empieza."""
    h = pd.DatetimeIndex(horas)
    nombre = np.where((h.hour >= 7) & (h.hour < 13), "mañana", np.where((h.hour >= 13) & (h.hour < 19), "tarde", "noche"))
    fecha = (h - pd.Timedelta(hours=7)).normalize()
    return fecha, nombre


def por_turno(df: pd.DataFrame, cols: list[str], claves: list[str] | None = None) -> pd.DataFrame:
    """Suma por (claves, fecha_turno, turno). Solo turnos completos (todas sus horas con dato)."""
    claves = claves or []
    fecha, nombre = turno_de(df["hora"])
    d = df.assign(fecha=fecha, turno=nombre)
    g = d.groupby(claves + ["fecha", "turno"], sort=False)
    out = g[cols].sum(min_count=1)
    out["n_horas"] = g[cols[0]].count()
    out = out.reset_index()
    out = out[out["n_horas"] == out["turno"].map(HORAS_TURNO)].drop(columns="n_horas")
    out["dia_semana"] = out["fecha"].dt.day_of_week
    return out


# --- umbrales e incertidumbre ------------------------------------------------------------------
def umbrales(hist_turnos: pd.DataFrame, hasta: pd.Timestamp | None = None,
             semanas: int = SEMANAS_REFERENCIA) -> pd.DataFrame:
    """Percentiles 75 y 90 por turno con las `semanas` anteriores a `hasta` (excluido)."""
    h = hist_turnos.dropna(subset=["real"])
    if hasta is not None:
        h = h[h["fecha"] < hasta]
    h = h[h["fecha"] >= h["fecha"].max() - pd.Timedelta(weeks=semanas)]
    u = h.groupby("turno")["real"].quantile([P_CARGADO, P_CRITICO]).unstack()
    u.columns = ["umbral_cargado", "umbral_critico"]
    u["n_turnos_ref"] = h.groupby("turno").size()
    return u.reindex(ORDEN_TURNOS).reset_index()


def alpha_turno(real, pred) -> float:
    """Dispersión NB2 de los totales por turno, estimada con errores de pronóstico fuera de muestra."""
    r, p = np.asarray(real, float), np.asarray(pred, float)
    ok = np.isfinite(r) & np.isfinite(p) & (p > 0)
    if ok.sum() < 5:
        return 0.0
    return float(max(np.sum((r[ok] - p[ok]) ** 2 - p[ok]) / np.sum(p[ok] ** 2), 0.0))


def prob_supera(mu, alpha: float, umbral) -> np.ndarray:
    """P(X > umbral) con X ~ NB2(mu, alpha) (Poisson si alpha ≈ 0)."""
    mu = np.maximum(np.asarray(mu, float), 1e-9)
    u = np.floor(np.asarray(umbral, float))
    if alpha > 1e-6:
        n = 1 / alpha
        return stats.nbinom.sf(u, n, n / (n + mu))
    return stats.poisson.sf(u, mu)


def intervalo(mu, alpha: float, nivel: float = 0.90):
    mu = np.maximum(np.asarray(mu, float), 1e-9)
    a = (1 - nivel) / 2
    if alpha > 1e-6:
        n = 1 / alpha
        q = n / (n + mu)
        return stats.nbinom.ppf(a, n, q), stats.nbinom.ppf(1 - a, n, q)
    return stats.poisson.ppf(a, mu), stats.poisson.ppf(1 - a, mu)


def colorear(p_cargado, p_critico) -> np.ndarray:
    p_cargado, p_critico = np.asarray(p_cargado), np.asarray(p_critico)
    return np.where(p_critico >= UMBRAL_ROJO, "rojo",
                    np.where((p_cargado >= UMBRAL_AMARILLO_CARGADO) | (p_critico >= UMBRAL_AMARILLO_CRITICO),
                             "amarillo", "verde"))


def categoria_real(real, u_cargado, u_critico) -> np.ndarray:
    real = np.asarray(real, float)
    return np.where(real > u_critico, "crítico", np.where(real > u_cargado, "cargado", "normal"))


def aplicar(turnos: pd.DataFrame, u: pd.DataFrame, alpha: float) -> pd.DataFrame:
    """Agrega umbrales, probabilidades, intervalo y color a una tabla con columna `pred` por turno."""
    t = turnos.merge(u[["turno", "umbral_cargado", "umbral_critico"]], on="turno", how="left")
    t["p_cargado"] = prob_supera(t["pred"], alpha, t["umbral_cargado"])
    t["p_critico"] = prob_supera(t["pred"], alpha, t["umbral_critico"])
    t["li"], t["ls"] = intervalo(t["pred"], alpha)
    t["color"] = colorear(t["p_cargado"], t["p_critico"])
    return t


# --- validación fuera de muestra ----------------------------------------------------------------
def validar(bt_horario: pd.DataFrame, hist_turnos: pd.DataFrame, modelo: str) -> pd.DataFrame:
    """Semáforo aplicado a las semanas del backtest de `modelo`. Umbrales con las 52 semanas previas al
    primer corte; dispersión dejando fuera la semana evaluada. Devuelve un turno por fila con color
    pronosticado y categoría real."""
    b = bt_horario[bt_horario["modelo"] == modelo]
    if b.empty:
        return pd.DataFrame()
    t = por_turno(b, ["real", "pred"], ["corte"])
    u = umbrales(hist_turnos, hasta=t["corte"].min())
    filas = []
    for c in t["corte"].unique():
        otras = t[t["corte"] != c]
        a = alpha_turno(otras["real"], otras["pred"])
        filas.append(aplicar(t[t["corte"] == c], u, a))
    v = pd.concat(filas, ignore_index=True)
    v["categoria_real"] = categoria_real(v["real"], v["umbral_cargado"], v["umbral_critico"])
    v["modelo"] = modelo
    return v


def metricas_semaforo(v: pd.DataFrame) -> dict:
    """Lo que importa para un jefe de urgencias:
    - sensibilidad_critico: de los turnos que fueron críticos, cuántos tenían alerta (amarillo o rojo)
    - precision_alerta: de los turnos con alerta, cuántos fueron al menos cargados
    - precision_rojo: de los rojos, cuántos fueron al menos cargados
    - criticos_en_verde: de los turnos críticos, cuántos quedaron en verde (lo peor que puede pasar)
    - tasa_alerta: qué fracción de turnos se marcan con alerta (si todo es alerta, nadie la atiende)
    - riesgo_critico_en_alerta / _en_verde: fracción de turnos críticos entre los que tuvieron alerta y entre
      los verdes (base por construcción ≈ 10 %): la alerta sirve si el primero es claramente mayor"""
    if v.empty:
        return {}
    crit = v["categoria_real"] == "crítico"
    alerta = v["color"].isin(["amarillo", "rojo"])
    rojo = v["color"] == "rojo"
    al_menos_cargado = v["categoria_real"].isin(["cargado", "crítico"])
    div = lambda a, b: float(a / b) if b else float("nan")  # noqa: E731
    return {"turnos": int(len(v)), "turnos_criticos": int(crit.sum()),
            "sensibilidad_critico": div((crit & alerta).sum(), crit.sum()),
            "precision_alerta": div((alerta & al_menos_cargado).sum(), alerta.sum()),
            "precision_rojo": div((rojo & al_menos_cargado).sum(), rojo.sum()),
            "criticos_en_verde": div((crit & ~alerta).sum(), crit.sum()),
            "tasa_alerta": div(alerta.sum(), len(v)),
            "riesgo_critico_en_alerta": div((crit & alerta).sum(), alerta.sum()),
            "riesgo_critico_en_verde": div((crit & ~alerta).sum(), (~alerta).sum())}


def matriz_confusion(v: pd.DataFrame) -> pd.DataFrame:
    m = pd.crosstab(pd.Categorical(v["color"], COLORES), pd.Categorical(v["categoria_real"], CATEGORIAS),
                    dropna=False)
    m.index.name, m.columns.name = "color_pronosticado", "categoria_real"
    return m.reset_index().melt(id_vars="color_pronosticado", var_name="categoria_real", value_name="turnos")


# --- protocolo -------------------------------------------------------------------------------
PROTOCOLO = [
    # serie, color, acción, responsable
    ("llegadas", "verde", "Operación normal. Revisar el semáforo de los próximos 3 días en la reunión diaria.",
     "Coordinación de urgencias"),
    ("llegadas", "amarillo", "Programar refuerzo escalonado en el turno (un profesional de apoyo para consulta). "
     "Dejar listo un consultorio adicional para habilitar si se llena la sala de espera. "
     "Reforzar admisiones en la primera hora del turno.", "Coordinación de urgencias"),
    ("llegadas", "rojo", "Activar el plan de saturación desde el turno anterior: consultorios adicionales "
     "habilitados, refuerzo de personal confirmado, apoyo a admisiones y verificación de derechos. "
     "Coordinar con la red de EPS la remisión ágil de los triajes IV-V.", "Dirección médica + coordinación de urgencias"),
    ("llegadas_hospitalizan", "verde", "Operación normal de camas.", "Gestión de camas"),
    ("llegadas_hospitalizan", "amarillo", "Ronda temprana en pisos para identificar altas del día antes de las 11 h. "
     "Reservar camas para los ingresos esperados desde urgencias en la franja.", "Gestión de camas + jefes de piso"),
    ("llegadas_hospitalizan", "rojo", "Altas priorizadas antes del mediodía, sala de egreso habilitada y gestor de camas "
     "dedicado desde la mañana. Revisar estancias largas en urgencias y en pisos para destrabar traslados.",
     "Dirección médica + gestión de camas"),
]


def protocolo() -> pd.DataFrame:
    return pd.DataFrame(PROTOCOLO, columns=["serie", "color", "accion", "responsable"])
