"""Calendario colombiano para las series: festivos (con la Ley Emiliani), puentes, Semana Santa,
Carnaval de Barranquilla y fin de año. Sirve como variables exógenas del pronóstico.
No usa datos del HUN: solo fechas del calendario."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

try:
    import holidays as _holidays
except ImportError:  # pragma: no cover - depende del entorno
    _holidays = None


def _pascua(anio: int) -> date:
    """Domingo de Pascua (algoritmo anónimo gregoriano)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mes = (h + l_ - 7 * m + 114) // 31
    dia = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(anio, mes, dia)


def festivos(anios) -> dict[date, str]:
    """Festivos nacionales de Colombia. Necesita el paquete `holidays` (está en requirements.txt)."""
    if _holidays is None:
        raise RuntimeError("Falta el paquete 'holidays': pip install -r requirements.txt")
    return dict(_holidays.Colombia(years=sorted(set(int(a) for a in anios))).items())


def tabla(desde, hasta) -> pd.DataFrame:
    """Una fila por día entre `desde` y `hasta` (incluidos) con las variables de calendario."""
    dias = pd.date_range(pd.Timestamp(desde).normalize(), pd.Timestamp(hasta).normalize(), freq="D")
    fest = festivos(range(dias.min().year, dias.max().year + 1)) if len(dias) else {}
    d = pd.DataFrame(index=dias)
    d.index.name = "fecha"
    fechas = [x.date() for x in dias]
    d["dia_semana"] = dias.dayofweek                   # 0 = lunes
    d["mes"] = dias.month
    d["anio"] = dias.year
    d["semana_anio"] = dias.isocalendar().week.to_numpy().astype(int)
    d["fin_de_semana"] = d["dia_semana"] >= 5
    d["festivo"] = [f in fest for f in fechas]
    d["nombre_festivo"] = [fest.get(f, "") for f in fechas]
    # Puente: sábado y domingo antes de un lunes festivo, y el lunes mismo
    lunes_fest = {f for f in fest if f.weekday() == 0}
    d["puente"] = [f in lunes_fest or (f + timedelta(days=2)) in lunes_fest and f.weekday() == 5
                   or (f + timedelta(days=1)) in lunes_fest and f.weekday() == 6 for f in fechas]
    d["despues_de_festivo"] = [(f - timedelta(days=1)) in fest and f not in fest for f in fechas]
    ss, carn = set(), set()
    for anio in range(dias.min().year if len(dias) else 0, (dias.max().year if len(dias) else -1) + 1):
        p = _pascua(anio)
        ss |= {p - timedelta(days=k) for k in range(0, 8)}            # Domingo de Ramos a Pascua
        miercoles_ceniza = p - timedelta(days=46)
        carn |= {miercoles_ceniza - timedelta(days=k) for k in range(1, 5)}   # sábado a martes de Carnaval
    d["semana_santa"] = [f in ss for f in fechas]
    d["carnaval"] = [f in carn for f in fechas]
    d["navidad_anio_nuevo"] = [(f.month == 12 and f.day >= 24) or (f.month == 1 and f.day == 1) for f in fechas]
    d["especial"] = d[["festivo", "puente", "semana_santa", "carnaval", "navidad_anio_nuevo"]].any(axis=1)
    return d


CATEGORIAS = {
    "festivo": "Festivo",
    "despues_de_festivo": "Día después de un festivo",
    "puente": "Puente (sáb-dom-lun festivo)",
    "semana_santa": "Semana Santa",
    "carnaval": "Carnaval de Barranquilla",
    "navidad_anio_nuevo": "24 dic - 1 ene",
}
