"""Resumen de la exploración SIN números ni datos de pacientes.

Lee los extractos 02, 08, 09 y 10 de DATA_DIR e imprime solo nombres
de conceptos, IDs del vocabulario y banderas sí/no. Es lo único que se
puede compartir fuera del equipo (p. ej. con Claude).

Uso:  python scripts/resumen_seguro.py
"""
from __future__ import annotations

import pandas as pd

from hun.palabras import extracto as _try


def _nombres(df: pd.DataFrame, max_n: int = 30) -> None:
    for _, r in df.head(max_n).iterrows():
        print(f"  - [{r['concept_id']}] {r['concept_name']}")
    if len(df) > max_n:
        print(f"  ... (+{len(df) - max_n} más)")


print("\n== 02 · Tipos de visita ==")
df = _try("02_tipos_visita_y_etapas")
if df is not None:
    _nombres(df[df["nivel"] == "visit"])
    print("\n== 02 · Etapas (visit_detail) ==")
    _nombres(df[df["nivel"] == "detail"])

print("\n== 08 · Conceptos que suenan a triaje ==")
df = _try("08_conceptos_triaje")
if df is not None:
    if df.empty:
        print("  (vacío)")
    else:
        for _, r in df.head(40).iterrows():
            print(f"  - [{r['concept_id']}] {r['concept_name']}  ({r['domain_id']})")

print("\n== 09 · Qué se mide en measurement (top 25, sin conteos) ==")
df = _try("09_conceptos_measurement")
if df is not None:
    for _, r in df.head(25).iterrows():
        texto = "sí" if r["con_texto"] > 0 else "no"
        print(f"  - [{r['concept_id']}] {r['concept_name']}  | trae texto fuente: {texto}")

print("\n== 10 · Texto que menciona triaje ==")
df = _try("10_texto_triaje")
if df is not None:
    print("  Hay coincidencias: " + ("sí" if not df.empty else "no"))
    if not df.empty:
        print("  (No copies los textos reales. Míralos tú con:")
        print("   python -c \"from hun.extract import load; print(load('10_texto_triaje').head(10).to_string())\"")
        print("   y descríbeme la FORMA con un valor inventado, ej: 'TRIAGE: <nivel>')")

print("\nTodo lo de arriba se puede compartir: son nombres e IDs del vocabulario, sin conteos.\n")
