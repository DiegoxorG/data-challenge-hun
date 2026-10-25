"""Exploración de series de tiempo para el pronóstico (llegadas, ingresos, altas y censos).

    python -m series_tiempo                 # corre las consultas 26-28 y arma el reporte
    python -m series_tiempo.resumen_seguro  # lo único que se comparte con Claude
    from series_tiempo import cargar        # series limpias para modelar
"""
from .datos import cargar

__all__ = ["cargar"]
