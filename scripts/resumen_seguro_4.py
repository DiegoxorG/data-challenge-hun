"""Resumen seguro (parte 4): episodios de urgencias, llegadas y ocupación.

Solo proporciones en palabras, franjas amplias de tiempo y comparaciones
cualitativas. Sin conteos, fechas de pacientes ni cifras exactas.
Se puede compartir.

Uso:  python scripts/resumen_seguro_4.py
"""
from __future__ import annotations

import pandas as pd

from hun.extract import load

CAPACIDAD_URGENCIAS = 58      # cubículos habilitados (salida de campo 1 oct)
CAPACIDAD_HOSPITAL = 64       # camas de hospitalización (salida de campo 1 oct)


def _try(nombre: str) -> pd.DataFrame | None:
    try:
        return load(nombre)
    except FileNotFoundError:
        print(f"  (no encontré {nombre}; córrelo con hun.extract)")
        return None


def cuanto(p: float) -> str:
    if pd.isna(p) or p == 0:
        return "ninguno"
    if p < 0.01:
        return "casi ninguno"
    if p < 0.10:
        return "pocos"
    if p < 0.50:
        return "bastantes"
    if p < 0.90:
        return "la mayoría"
    return "casi todos"


def franja(minutos: float) -> str:
    if pd.isna(minutos):
        return "sin dato"
    for limite, etiqueta in [(15, "menos de 15 min"), (60, "15 min-1 h"), (240, "1-4 h"),
                             (720, "4-12 h"), (1440, "12-24 h"), (4320, "1-3 días"),
                             (10080, "3-7 días")]:
        if minutos < limite:
            return etiqueta
    return "más de 7 días"


def veces(a: float, b: float) -> str:
    """Compara a contra b en palabras."""
    if pd.isna(a) or pd.isna(b) or b <= 0:
        return "no se puede comparar"
    r = a / b
    if r < 0.8:
        return "MENOS que"
    if r < 1.25:
        return "parecido a"
    if r < 1.5:
        return "algo más que"
    if r < 3:
        return "bastante más que (1.5 a 3 veces)"
    return "mucho más que (más de 3 veces)"


print("\n== 20 · Episodios ==")
df = _try("20_resumen_episodios")
if df is not None:
    total = df["n"].sum()
    for _, r in df.iterrows():
        print(f"  - {r['origen']} / {r['destino']}  (peso: {cuanto(r['n'] / total)})")
        if r["origen"] == "urgencias":
            print(f"      tiempo en urgencias  p25: {franja(r['p25_min_urg'])} | p50: {franja(r['p50_min_urg'])}"
                  f" | p75: {franja(r['p75_min_urg'])} | p90: {franja(r['p90_min_urg'])}")
            print(f"      con tiempo 0: {cuanto(r['p_urg_cero'])} | más de 24 h en urgencias: {cuanto(r['p_urg_mas_24h'])}")
        if r["destino"] == "hospitalizado":
            print(f"      estancia hospitalaria  p50: {franja(r['p50_min_hosp'])} | p90: {franja(r['p90_min_hosp'])}")
        if r["origen"] != "urgencias":
            print(f"      empiezan dentro de 48 h tras una urgencia: {cuanto(r['p_tras_urgencia_48h'])}")
    urg = df[df["origen"] == "urgencias"].set_index("destino")
    if {"alta", "hospitalizado"} <= set(urg.index):
        print(f"\n  >> Los que se hospitalizan pasan en urgencias (mediana) "
              f"{veces(urg.loc['hospitalizado', 'p50_min_urg'], urg.loc['alta', 'p50_min_urg'])} los de alta.")
        print(f"     De los que llegan a urgencias, se hospitalizan: "
              f"{cuanto(urg.loc['hospitalizado', 'n'] / urg['n'].sum())}")

print("\n== 21 · Serie de llegadas por hora (salud de la serie) ==")
df = _try("21_llegadas_por_hora")
if df is not None:
    df["hora"] = pd.to_datetime(df["hora"])
    s = df.set_index("hora")["llegadas"].asfreq("h", fill_value=0)
    print(f"  horas sin ninguna llegada: {cuanto((s == 0).mean())}")
    diario = s.resample("D").sum()
    print(f"  días completos sin llegadas (posibles huecos de datos): {cuanto((diario == 0).mean())}")
    mensual = s.resample("MS").sum()
    if len(mensual) > 2:
        mensual = mensual.iloc[1:-1]                 # el primer y último mes suelen estar incompletos
        bajos = mensual[mensual < 0.5 * mensual.median()]
        print(f"  meses con volumen anormalmente bajo (<50% de la mediana): {cuanto(len(bajos) / len(mensual))}")
        if len(bajos):
            print("     cuáles: " + ", ".join(f"{m:%Y-%m}" for m in bajos.index[:12]))
    perfil = s.groupby(s.index.hour).mean()
    print(f"  ¿la demanda cambia a lo largo del día? la hora más cargada recibe "
          f"{veces(perfil.max(), perfil.min())} la más tranquila")
    semanal = s.groupby(s.index.dayofweek).mean()
    print(f"  ¿y entre días de la semana? el día más cargado recibe "
          f"{veces(semanal.max(), semanal.min())} el más tranquilo")

print("\n== 22 · ¿El tiempo en urgencias depende de la hora de llegada? ==")
df = _try("22_tiempo_urgencias_por_franja")
if df is not None:
    for destino, g in df.groupby("destino"):
        sumas = g.assign(w=g["p50_min_urg"] * g["n"]).groupby("hora")[["w", "n"]].sum()
        por_hora = sumas["w"] / sumas["n"]          # mediana ponderada aproximada por hora
        print(f"  - {destino}: la peor hora de llegada tiene una mediana "
              f"{veces(por_hora.max(), por_hora.min())} la mejor")

print("\n== 23 · Ocupación hora a hora ==")
df = _try("23_ocupacion_por_hora")
if df is not None:
    df["hora"] = pd.to_datetime(df["hora"])
    print(f"  ¿hay horas con ocupación negativa (error de lógica)? "
          f"{'sí' if (df[['en_urgencias', 'en_hospitalizacion']] < 0).any().any() else 'no'}")
    df = df[df["hora"] >= df["hora"].min() + pd.Timedelta(days=30)]   # quitar arranque (calentamiento)
    print(f"  horas con urgencias por encima de {CAPACIDAD_URGENCIAS} pacientes: "
          f"{cuanto((df['en_urgencias'] > CAPACIDAD_URGENCIAS).mean())}")
    print(f"  horas con hospitalización por encima de {CAPACIDAD_HOSPITAL} camas: "
          f"{cuanto((df['en_hospitalizacion'] > CAPACIDAD_HOSPITAL).mean())}")
    print(f"  ocupación típica de urgencias vs capacidad: {veces(df['en_urgencias'].median(), CAPACIDAD_URGENCIAS)} la capacidad")
    print(f"  ocupación típica de hospitalización vs capacidad: {veces(df['en_hospitalizacion'].median(), CAPACIDAD_HOSPITAL)} la capacidad")

print("\nTodo lo de arriba se puede compartir: proporciones en palabras, franjas y comparaciones cualitativas.")
print("Excepción a revisar tú: la lista de meses con volumen bajo (son fechas de cobertura, no de pacientes).\n")