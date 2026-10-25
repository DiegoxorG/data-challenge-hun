"""Traducción de cifras a palabras para los resúmenes seguros: lo único que se comparte con Claude.

Todos los resúmenes (scripts/resumen_seguro*.py, Cuellos_botella y series_tiempo) usan estas
mismas funciones, así que "pocos" o "1-4 h" significan lo mismo en todas partes.
"""
from __future__ import annotations

import pandas as pd


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
    if minutos < 0:
        return "solape de " + franja(-minutos)
    if minutos == 0:
        return "0 (contiguo)"
    for limite, etiqueta in [(1, "menos de 1 min"), (15, "1-15 min"), (60, "15 min-1 h"), (240, "1-4 h"),
                             (720, "4-12 h"), (1440, "12-24 h"), (4320, "1-3 días"), (10080, "3-7 días"),
                             (43200, "1-4 semanas")]:
        if minutos < limite:
            return etiqueta
    return "más de un mes"


def veces(a: float, b: float) -> str:
    if pd.isna(a) or pd.isna(b) or b <= 0:
        return "no comparable con"
    r = a / b
    for limite, txt in [(0.5, "menos de la mitad de"), (0.8, "menos que"), (1.25, "parecido a"),
                        (1.5, "algo más que (1.25 a 1.5 veces)"), (3, "bastante más que (1.5 a 3 veces)"),
                        (10, "mucho más que (3 a 10 veces)")]:
        if r < limite:
            return txt
    return "muchísimo más que (más de 10 veces)"


def es(a: float, b: float) -> str:
    """'es parecido a', 'es bastante más que (...)' o 'no es comparable con'."""
    v = veces(a, b)
    return "no es comparable con" if v == "no comparable con" else "es " + v


def extracto(nombre: str) -> pd.DataFrame | None:
    """Carga un extracto de DATA_DIR; si no existe, avisa cómo generarlo y devuelve None."""
    from .extract import load
    try:
        return load(nombre)
    except FileNotFoundError:
        print(f"  (no encontré {nombre}; córrelo con hun.extract)")
        return None
