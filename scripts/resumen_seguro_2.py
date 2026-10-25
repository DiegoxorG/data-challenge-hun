"""Resumen seguro (parte 2): triaje, calidad de tiempos y segmentos.

Solo nombres de conceptos y proporciones en palabras (ninguno / pocos /
la mayoría...). Sin conteos. Se puede compartir fuera del equipo.

Uso:  python scripts/resumen_seguro_2.py
"""
from __future__ import annotations

from hun.palabras import cuanto, extracto as _try


print("\n== 11 · ¿Se usan los conceptos de triaje en los datos? ==")
df = _try("11_uso_conceptos_triaje")
if df is not None:
    nombres = {45949550: "Triage level", 3119360: "Seen by triage nurse",
               3104237: "Seen by triage nurse", 3045729: "Treatment urgency"}
    if df.empty:
        print("  Ninguno aparece en ninguna tabla.")
    for _, r in df.iterrows():
        print(f"  - [{r['concept_id']}] {nombres.get(r['concept_id'], '?')} -> aparece en {r['tabla']}")

print("\n== 12 · Calidad de los tiempos (proporción de registros) ==")
df = _try("12_granularidad_tiempos")
if df is not None:
    for _, r in df.iterrows():
        print(f"  - {r['tabla']} / {r['tipo']}:")
        print(f"      inicio a las 00:00 = {cuanto(r['p_inicio_medianoche'])} | "
              f"fin a las 00:00 = {cuanto(r['p_fin_medianoche'])}")
        print(f"      duración cero = {cuanto(r['p_duracion_cero'])} | "
              f"más de 30 días = {cuanto(r['p_mas_30_dias'])}")

print("\n== 13 · Segmentos dentro de cada tipo de visita ==")
df = _try("13_visita_vs_segmento")
if df is not None:
    for tipo, g in df.groupby("tipo_visita", sort=False):
        total = g["n"].sum()
        partes = [f"{r['segmento']} ({cuanto(r['n'] / total)})" for _, r in g.iterrows()]
        print(f"  - {tipo}: " + "; ".join(partes))

print("\n== 14 · Segmentos por visita ==")
df = _try("14_segmentos_por_visita")
if df is not None:
    total = df["visitas"].sum()
    uno = df.loc[df["n_segmentos"] == 1, "visitas"].sum() / total
    dos = df.loc[df["n_segmentos"] == 2, "visitas"].sum() / total
    mas = df.loc[df["n_segmentos"] >= 3, "visitas"].sum() / total
    print(f"  1 segmento = {cuanto(uno)} | 2 segmentos = {cuanto(dos)} | 3 o más = {cuanto(mas)}")
    print(f"  ¿Hay visitas con 10+ segmentos? {'sí' if (df['n_segmentos'] >= 10).any() else 'no'}")

print("\nTodo lo de arriba se puede compartir: nombres y proporciones en palabras, sin conteos.\n")
