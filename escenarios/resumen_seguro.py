"""Resumen seguro de los escenarios: solo palabras y franjas. Uso: python -m escenarios.resumen_seguro"""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from .__main__ import carpeta_salida

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def pct(x: float) -> str:
    if pd.isna(x):
        return "sin dato"
    x = x * 100
    for lim, t in [(2, "menos de 2 %"), (5, "2-5 %"), (10, "5-10 %"), (20, "10-20 %"), (30, "20-30 %"), (50, "30-50 %")]:
        if x < lim:
            return t
    return "más de 50 %"


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=None)
    sal = carpeta_salida(ap.parse_args(argv).salida)
    pb = sal / "powerbi"
    if not (sal / "meta.json").exists():
        print("No encontré la corrida; corre primero python -m escenarios.")
        return 1
    meta = json.loads((sal / "meta.json").read_text(encoding="utf-8"))
    r = pd.read_csv(pb / "resumen_espera_cama.csv").set_index("reduccion_espera_h")
    e = pd.read_csv(pb / "escenario_espera_cama.csv")
    a = pd.read_csv(pb / "escenario_altas_temprano.csv")
    f0, f1 = meta["franja_pico"]
    print("RESUMEN SEGURO DE ESCENARIOS (solo palabras y franjas)\n")
    print("== Escenario 1: reducir la espera de cama de los pacientes que suben desde urgencias ==")
    print(f"- Franja de mayor censo en urgencias (promedio de la semana): {f0:02d}-{f1:02d} h.")
    for h in (2, 4, 6, 8, 12):
        if h in r.index:
            print(f"- Reducir {h} h: censo de urgencias baja {pct(r.loc[h, 'reduccion_pct'])} en promedio "
                  f"y {pct(r.loc[h, 'reduccion_pct_pico'])} en la franja pico.")
    e4 = e[e["reduccion_espera_h"] == 4].copy()
    e4["pct"] = e4["reduccion_censo"] / e4["censo_urgencias_base"].where(e4["censo_urgencias_base"] > 0)
    top = e4.nlargest(3, "pct")
    print("- Con 4 h, donde más baja (relativo): " +
          "; ".join(f"{DIAS[int(x.dia_semana)]} {int(x.hora_dia):02d}h" for x in top.itertuples()) + ".")
    print("\n== Escenario 2: adelantar altas de cama de la tarde ==")
    base = a[(a["fraccion_altas"] == 0) & (a["adelanto_h"] == 4)]["censo_hosp_base"].mean()
    for d in (2, 4, 6):
        for f in (0.25, 0.5):
            s = a[(a["adelanto_h"] == d) & (a["fraccion_altas"] == f)]
            m = s[s["hora_dia"].between(8, 12)]
            print(f"- Adelantar {int(f * 100)} % de las altas de la tarde {d} h: en la mañana (8-12 h) "
                  f"quedan libres {pct(m['camas_liberadas'].mean() / max(m['censo_hosp_base'].mean(), 1e-9))} "
                  f"de las camas ocupadas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
