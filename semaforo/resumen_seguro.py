"""Resumen seguro del semáforo: solo palabras, franjas y conteos de turnos del pronóstico (no de pacientes).
Uso: python -m semaforo.resumen_seguro"""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from .__main__ import carpeta

NOM = {"naive_semanal": "naïve (misma hora semana pasada)", "glm": "GLM", "glm_nivel": "GLM + nivel reciente"}
SER = {"llegadas": "llegadas a urgencias", "llegadas_hospitalizan": "llegadas que se hospitalizan (camas)"}


def pct(x) -> str:
    if pd.isna(x):
        return "sin dato (no hubo casos)"
    x = x * 100
    for lim, t in [(10, "menos de 10 %"), (25, "10-25 %"), (50, "25-50 %"), (75, "50-75 %"), (90, "75-90 %")]:
        if x < lim:
            return t
    return "más de 90 %"


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=None)
    sal = carpeta(ap.parse_args(argv).salida, "semaforo", "La salida")
    if not (sal / "meta.json").exists():
        print("No encontré la corrida; corre primero python -m semaforo.")
        return 1
    pb = sal / "powerbi"
    met = pd.read_csv(pb / "semaforo_metricas.csv")
    fut = pd.read_csv(pb / "semaforo_futuro.csv")
    print("RESUMEN SEGURO DEL SEMÁFORO (solo palabras y franjas)\n")
    for serie in met["serie"].unique():
        print(f"== {SER.get(serie, serie)} ==")
        m = met[met["serie"] == serie].set_index("modelo")
        for mod, r in m.iterrows():
            et = " [elegido]" if r["es_elegido"] else " [referencia]"
            print(f"- Validación con {NOM.get(mod, mod)}{et}:")
            print(f"    turnos críticos anticipados (amarillo o rojo): {pct(r['sensibilidad_critico'])}")
            print(f"    turnos críticos que quedaron en verde: {pct(r['criticos_en_verde'])}")
            print(f"    alertas que sí fueron turnos cargados o críticos: {pct(r['precision_alerta'])}")
            print(f"    rojos que sí fueron cargados o críticos: {pct(r['precision_rojo'])}")
            print(f"    fracción de turnos con alerta: {pct(r['tasa_alerta'])}")
            print(f"    turnos críticos entre los que tuvieron alerta: {pct(r['riesgo_critico_en_alerta'])}; "
                  f"entre los verdes: {pct(r['riesgo_critico_en_verde'])} (un turno cualquiera: cerca de 10 %)")
            hay = "hubo" if r["turnos_criticos"] > 0 else "NO hubo"
            print(f"    en las semanas de prueba {hay} turnos críticos.")
        f = fut[fut["serie"] == serie]
        cuenta = f["color"].value_counts()
        print(f"- Próximos días: {int(cuenta.get('rojo', 0))} turnos rojos, {int(cuenta.get('amarillo', 0))} amarillos, "
              f"{int(cuenta.get('verde', 0))} verdes (de {len(f)} turnos).")
        alertas = f[f["color"] != "verde"]
        if len(alertas):
            g = alertas.groupby(["dia_nombre", "turno"]).size().sort_values(ascending=False).head(4)
            print("- Dónde caen las alertas: " + "; ".join(f"{d} {t}" for (d, t) in g.index) + ".")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
