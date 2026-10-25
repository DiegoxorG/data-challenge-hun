"""Resumen seguro (parte 5): diagnóstico de la ocupación.

Explica por qué la ocupación calculada en 23 supera la capacidad, comparando
hipótesis. Solo palabras, franjas y comparaciones cualitativas. Se puede compartir.

Uso:  python scripts/resumen_seguro_5.py
"""
from __future__ import annotations

import pandas as pd

from hun.palabras import cuanto, franja, veces, extracto as _try

CAPACIDAD_URGENCIAS = 58
CAPACIDAD_HOSPITAL = 64


print("\n== 24 · Diagnóstico ==")
d = _try("24_diagnostico_ocupacion")
if d is not None:
    r = d.iloc[0]
    print("  H1 · ¿Urgencias sigue abierto después del ingreso a hospitalización?")
    print(f"      hospitalizados con urgencias abierto tras el ingreso: {cuanto(r['p_urg_sigue_tras_ingreso'])}")
    print(f"      cuánto sigue abierto (mediana): {franja(r['p50_min_urg_tras_ingreso'])}")
    print(f"      urgencias abierto durante TODA la hospitalización: {cuanto(r['p_urg_cubre_toda_hosp'])}")
    print("  H2 · ¿Episodios eternos?")
    print(f"      episodios de urgencias > 3 días: {cuanto(r['p_epis_urg_mas_3d'])} | > 7 días: "
          f"{cuanto(r['p_epis_urg_mas_7d'])} | > 30 días: {cuanto(r['p_epis_urg_mas_30d'])}")
    print(f"      parte de las horas-paciente en urgencias que viene de episodios > 24 h: "
          f"{cuanto(r['p_horas_urg_de_epis_mas_24h'])} | de episodios > 7 días: {cuanto(r['p_horas_urg_de_epis_mas_7d'])}")
    print(f"      hospitalizaciones > 30 días: {cuanto(r['p_hosp_mas_30d'])}")
    print("  Otros")
    print(f"      episodios de alta de menos de 15 min (¿solo registro?): {cuanto(r['p_alta_menos_15min'])}")
    print(f"      hueco urgencias -> hospitalización (cuando llega en < 48 h), mediana: "
          f"{franja(r['p50_min_hueco_urg_hosp_48h'])} | menos de 6 h: {cuanto(r['p_hueco_menos_6h'])}")

print("\n== 23 vs 25 · Ocupación original vs ajustada ==")
crudo, aj = _try("23_ocupacion_por_hora"), _try("25_ocupacion_ajustada")
for nombre, df in [("original (23)", crudo), ("ajustada (25)", aj)]:
    if df is None:
        continue
    df = df.copy()
    df["hora"] = pd.to_datetime(df["hora"])
    df = df[df["hora"] >= df["hora"].min() + pd.Timedelta(days=30)]
    df = df[df["hora"] < df["hora"].max() - pd.Timedelta(days=60)]   # últimos meses suelen venir incompletos
    print(f"  - {nombre}")
    print(f"      urgencias típica vs {CAPACIDAD_URGENCIAS} cubículos: {veces(df['en_urgencias'].median(), CAPACIDAD_URGENCIAS)} la capacidad"
          f" | horas por encima: {cuanto((df['en_urgencias'] > CAPACIDAD_URGENCIAS).mean())}")
    print(f"      hospitalización típica vs {CAPACIDAD_HOSPITAL} camas: {veces(df['en_hospitalizacion'].median(), CAPACIDAD_HOSPITAL)} la capacidad"
          f" | horas por encima: {cuanto((df['en_hospitalizacion'] > CAPACIDAD_HOSPITAL).mean())}")
    # ¿El censo crece sin parar? (señal de salidas que faltan)
    anual = df.set_index("hora").resample("YS").median()
    if len(anual) >= 2:
        print(f"      ¿crece sin parar? último año vs primero — urgencias: "
              f"{veces(anual['en_urgencias'].iloc[-1], anual['en_urgencias'].iloc[0])} | hospitalización: "
              f"{veces(anual['en_hospitalizacion'].iloc[-1], anual['en_hospitalizacion'].iloc[0])}")

print("\nTodo lo de arriba se puede compartir: palabras, franjas y comparaciones cualitativas.\n")
