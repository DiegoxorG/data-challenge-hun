"""Escenarios de mejora calculados con perfiles promedio por hora de la semana (sin pacientes).

1. Reducir la espera de cama h horas (palanca: gestión de camas / asignación anticipada).
   Si cada paciente que pasa de urgencias a cama sale de urgencias h horas antes, en la hora t ya no
   están en urgencias los que iban a subir entre t+1 y t+h:
       reducción_censo_urgencias(t) = Σ_{k=1..h} ingresos_desde_urgencias(t + k)
   Es la ley de Little hora por hora: en promedio baja (ingresos desde urgencias por hora) × h.
   Supone que esos pacientes esperaban al menos h horas: es un techo del efecto, no un piso.

2. Altas de cama más temprano (palanca: altas antes del mediodía).
   Una fracción p de las altas de la tarde (12-20 h) se adelanta d horas. Cada cama queda libre d
   horas antes:
       camas_liberadas(t) = p × Σ_{k=1..d} altas_tarde(t + k)
   Son camas disponibles en la mañana, justo cuando urgencias acumula pacientes esperando.

Todo se calcula sobre horas `completo` y se expresa por hora de la semana (lunes 0 h ... domingo 23 h).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

H_SEMANA = 168
REDUCCIONES_H = list(range(0, 13))           # horas de espera de cama que se reducen
FRACCIONES = [0.0, 0.25, 0.5, 0.75, 1.0]     # fracción de altas de la tarde que se adelanta
ADELANTO_H = [2, 4, 6]                       # horas que se adelanta cada alta
TARDE = range(12, 21)                        # altas que cuentan como "de la tarde"
DIAS_CALENTAMIENTO = 14                      # el censo acumulado arranca en 0: se descartan los primeros días

COLUMNAS = ["ingresos_desde_urgencias", "altas_cama", "censo_urgencias", "censo_hospitalizacion"]


def perfil(horas: pd.DataFrame, completo: pd.Series) -> pd.DataFrame:
    """Promedio por hora de la semana de las columnas necesarias, solo con horas completas y
    después del calentamiento del censo."""
    h = horas.loc[completo.to_numpy(), COLUMNAS].astype(float)
    h = h[h.index >= horas.index.min() + pd.Timedelta(days=DIAS_CALENTAMIENTO)]
    how = h.index.dayofweek * 24 + h.index.hour
    p = h.groupby(how).mean().reindex(range(H_SEMANA))
    p["altas_tarde"] = np.where(np.isin(np.arange(H_SEMANA) % 24, list(TARDE)), p["altas_cama"], 0.0)
    p.index.name = "how"
    return p


def _suma_siguientes(x: np.ndarray, h: int) -> np.ndarray:
    """Para cada hora t, suma de x(t+1..t+h) con la semana circular (domingo 23 h → lunes 0 h)."""
    if h <= 0:
        return np.zeros_like(x)
    return sum(np.roll(x, -k) for k in range(1, h + 1))


def espera_cama(p: pd.DataFrame) -> pd.DataFrame:
    ing = p["ingresos_desde_urgencias"].to_numpy()
    base = p["censo_urgencias"].to_numpy()
    filas = []
    for h in REDUCCIONES_H:
        red = np.minimum(_suma_siguientes(ing, h), base)
        filas.append(pd.DataFrame({"how": np.arange(H_SEMANA), "reduccion_espera_h": h,
                                   "censo_urgencias_base": base, "reduccion_censo": red,
                                   "censo_urgencias_escenario": base - red}))
    return _con_dia_hora(pd.concat(filas, ignore_index=True))


def altas_temprano(p: pd.DataFrame) -> pd.DataFrame:
    alt = p["altas_tarde"].to_numpy()
    base = p["censo_hospitalizacion"].to_numpy()
    filas = []
    for d in ADELANTO_H:
        sig = _suma_siguientes(alt, d)
        for f in FRACCIONES:
            lib = np.minimum(f * sig, base)
            filas.append(pd.DataFrame({"how": np.arange(H_SEMANA), "adelanto_h": d, "fraccion_altas": f,
                                       "censo_hosp_base": base, "camas_liberadas": lib,
                                       "censo_hosp_escenario": base - lib}))
    return _con_dia_hora(pd.concat(filas, ignore_index=True))


def _con_dia_hora(df: pd.DataFrame) -> pd.DataFrame:
    df.insert(1, "dia_semana", df["how"] // 24)      # 0 = lunes
    df.insert(2, "hora_dia", df["how"] % 24)
    return df


def resumen_espera(e: pd.DataFrame, franja: tuple[int, int] | None = None) -> pd.DataFrame:
    """Por reducción h: censo promedio base y escenario (toda la semana y en la franja pico)."""
    if franja is None:
        b = e[e["reduccion_espera_h"] == 0].groupby("hora_dia")["censo_urgencias_base"].mean()
        pico = int(b.idxmax())
        franja = (max(pico - 2, 0), min(pico + 2, 23))
    en = e["hora_dia"].between(*franja)
    out = e.groupby("reduccion_espera_h").agg(base=("censo_urgencias_base", "mean"),
                                              escenario=("censo_urgencias_escenario", "mean"))
    pk = e[en].groupby("reduccion_espera_h").agg(base_pico=("censo_urgencias_base", "mean"),
                                                 escenario_pico=("censo_urgencias_escenario", "mean"))
    out = out.join(pk)
    out["reduccion_pct"] = 1 - out["escenario"] / out["base"]
    out["reduccion_pct_pico"] = 1 - out["escenario_pico"] / out["base_pico"]
    out.attrs["franja"] = franja
    return out.reset_index()
