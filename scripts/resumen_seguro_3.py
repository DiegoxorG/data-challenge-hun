"""Resumen seguro (parte 3): duraciones, orden y transiciones de segmentos.

Solo nombres de conceptos, proporciones en palabras y franjas de tiempo
("entre 1 y 4 horas"). Sin conteos ni cifras exactas. Se puede compartir.

Uso:  python scripts/resumen_seguro_3.py
"""
from __future__ import annotations

import pandas as pd

from hun.palabras import cuanto, franja, extracto as _try


def _franjas(r: pd.Series, cols: dict[str, str]) -> str:
    """Lista solo las franjas que no son 'ninguno'."""
    partes = [f"{etq}: {cuanto(r[c])}" for c, etq in cols.items() if cuanto(r[c]) != "ninguno"]
    return " | ".join(partes) if partes else "(sin datos)"


print("\n== 15 · ¿Cuánto dura cada tipo de segmento? ==")
df = _try("15_duracion_por_segmento")
if df is not None:
    cols = {"p_cero": "dura 0", "p_menos_15min": "<15 min", "p_15_60min": "15-60 min",
            "p_1_4h": "1-4 h", "p_4_12h": "4-12 h", "p_12_24h": "12-24 h",
            "p_1_7dias": "1-7 días", "p_mas_7dias": ">7 días"}
    for _, r in df.iterrows():
        print(f"  - {r['segmento']}")
        print(f"      duración típica (sin contar los de 0): {franja(r['mediana_min_sin_ceros'])}")
        print(f"      reparto: {_franjas(r, cols)}")

print("\n== 16 · En visitas de urgencias, ¿qué segmento va primero y cuál último? ==")
df = _try("16_primero_ultimo_en_urgencias")
if df is not None:
    for pos, g in df.groupby("posicion", sort=False):
        total = g["n"].sum()
        partes = [f"{r['segmento']} ({cuanto(r['n'] / total)})" for _, r in g.iterrows()]
        print(f"  - {pos}: " + "; ".join(partes))

print("\n== 17 · ¿Cómo se encadenan los segmentos? (top 12 pares, de más a menos frecuente) ==")
df = _try("17_transiciones")
if df is not None:
    total = df["n"].sum()
    cols = {"p_solapado": "solapados", "p_seguido": "seguidos", "p_hueco_menos_1h": "hueco <1 h",
            "p_hueco_1_6h": "hueco 1-6 h", "p_hueco_6_24h": "hueco 6-24 h",
            "p_hueco_mas_1dia": "hueco >1 día"}
    for i, (_, r) in enumerate(df.head(12).iterrows(), 1):
        print(f"  {i:>2}. {r['desde']} -> {r['hacia']}  (peso: {cuanto(r['n'] / total)})")
        print(f"      {_franjas(r, cols)}")

print("\n== 18 · ¿La visita calza con sus segmentos? ==")
df = _try("18_visita_vs_segmentos")
if df is not None:
    cols = {"p_span_cero": "dura 0", "p_span_menos_4h": "<4 h", "p_span_4_24h": "4-24 h",
            "p_span_1_7dias": "1-7 días", "p_span_mas_7dias": ">7 días"}
    for _, r in df.iterrows():
        print(f"  - {r['tipo_visita']}")
        print(f"      visitas sin segmentos: {cuanto(r['p_sin_segmentos'])} | "
              f"inicio de la visita = inicio del 1er segmento: {cuanto(r['p_inicio_coincide'])}")
        print(f"      duración real típica: {franja(r['mediana_span_min'])} | reparto: {_franjas(r, cols)}")

print("\nTodo lo de arriba se puede compartir: nombres, proporciones en palabras y franjas amplias.\n")
