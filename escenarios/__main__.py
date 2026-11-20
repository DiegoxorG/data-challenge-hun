"""Uso:
    python -m escenarios [--salida <carpeta>] [--series-dir <carpeta>] [--excluir-ultimas-semanas 6]

Lee las series horarias de `python -m series_tiempo` y calcula los escenarios de escenarios/calculo.py.
Escribe en DATA_DIR/escenarios (nunca en el repo):
  powerbi/escenario_espera_cama.csv      hora de la semana × horas de reducción de la espera de cama
  powerbi/escenario_altas_temprano.csv   hora de la semana × adelanto × fracción de altas adelantadas
  powerbi/resumen_espera_cama.csv        efecto promedio y en la franja pico por cada reducción
  meta.json
No se conecta a la base. En consola solo imprime avance, sin cifras de los datos.
"""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from . import calculo as C

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def carpeta_salida(ruta=None):
    from pathlib import Path
    from hun.config import validar_carpeta
    if ruta is None:
        from hun.config import data_dir
        d = data_dir() / "escenarios"
    else:
        d = Path(ruta)
    d = validar_carpeta(d, "La salida")
    (d / "powerbi").mkdir(parents=True, exist_ok=True)
    return d


def correr(horas: pd.DataFrame, salida, excluir_ultimas_semanas: int = 0) -> dict:
    completo = horas["completo"].fillna(False).astype(bool)
    if excluir_ultimas_semanas > 0 and completo.any():
        fin = horas.index[completo.to_numpy()].max()
        completo = completo & (horas.index <= fin - pd.Timedelta(weeks=excluir_ultimas_semanas))
    faltan = [c for c in C.COLUMNAS if c not in horas]
    if faltan:
        raise RuntimeError(f"Faltan columnas en las series horarias: {faltan}. Corre de nuevo python -m series_tiempo.")
    p = C.perfil(horas, completo)
    e = C.espera_cama(p)
    a = C.altas_temprano(p)
    r = C.resumen_espera(e)
    pb = salida / "powerbi"
    e.to_csv(pb / "escenario_espera_cama.csv", index=False)
    a.to_csv(pb / "escenario_altas_temprano.csv", index=False)
    r.to_csv(pb / "resumen_espera_cama.csv", index=False)
    meta = {"excluir_ultimas_semanas": excluir_ultimas_semanas, "franja_pico": list(r.attrs["franja"]),
            "tarde": [min(C.TARDE), max(C.TARDE)]}
    (salida / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m escenarios", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", default=None)
    ap.add_argument("--series-dir", default=None)
    ap.add_argument("--excluir-ultimas-semanas", type=int, default=6)
    a = ap.parse_args(argv)
    sal = carpeta_salida(a.salida)
    print(f"Salida: {sal}\n· cargando las series de series_tiempo")
    from series_tiempo import cargar
    correr(cargar(a.series_dir)["horas"], sal, a.excluir_ultimas_semanas)
    print(f"Listo. Tablas para Power BI en: {sal / 'powerbi'}")
    print("Para compartir con Claude usa SOLO: python -m escenarios.resumen_seguro")
    return 0


if __name__ == "__main__":
    sys.exit(main())
