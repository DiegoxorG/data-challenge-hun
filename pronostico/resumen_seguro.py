"""Resumen seguro del pronóstico: SOLO palabras, franjas y comparaciones ("menor (0.5 a 0.8 veces)",
"10-20 %", "pico a las 10h"). Sin conteos, sin fechas, sin valores. Es lo único que se comparte con Claude.

Uso:  python -m pronostico.resumen_seguro [--salida <carpeta>]
"""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from .__main__ import carpeta_salida

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
NOMBRES = {"naive_semanal": "línea base 'misma hora de la semana pasada'",
           "promedio_semanal": "línea base 'promedio de las últimas 4 semanas'",
           "glm": "GLM (calendario + tendencia)",
           "glm_nivel": "GLM con nivel reciente (calendario + nivel de las últimas 4 semanas)"}
EFECTOS = {"festivo": "un festivo", "despues_de_festivo": "el día después de un festivo",
           "puente": "un día de puente", "semana_santa": "Semana Santa", "carnaval": "Carnaval",
           "navidad_anio_nuevo": "24 dic - 1 ene"}


def comparar(a: float, b: float) -> str:
    if pd.isna(a) or pd.isna(b) or b <= 0:
        return "no comparable"
    r = a / b
    for lim, txt in [(0.5, "mucho menor (menos de la mitad)"), (0.8, "menor (0.5 a 0.8 veces)"),
                     (0.95, "algo menor (0.8 a 0.95 veces)"), (1.05, "parecido"), (1.25, "algo mayor (1.05 a 1.25 veces)"),
                     (1.5, "mayor (1.25 a 1.5 veces)"), (3, "bastante mayor (1.5 a 3 veces)")]:
        if r < lim:
            return txt
    return "mucho mayor (más de 3 veces)"


def pct(x: float) -> str:
    if pd.isna(x):
        return "sin dato"
    x = abs(x) * 100
    for lim, txt in [(5, "menos de 5 %"), (10, "5-10 %"), (20, "10-20 %"), (30, "20-30 %"), (50, "30-50 %")]:
        if x < lim:
            return txt
    return "más de 50 %"


def mejora(mase: float) -> str:
    """MASE del modelo frente a la naive, dicho como cuánto baja el error."""
    if pd.isna(mase):
        return "sin dato"
    if mase >= 1.0:
        return "no le gana (error igual o mayor)"
    return "baja el error " + pct(1 - mase)


def cobertura(c: float, nivel: float, unidad: str = "horas") -> str:
    if pd.isna(c):
        return "sin dato"
    d = c - nivel
    txt = ("bien calibrado" if abs(d) < 0.03 else "algo ancho (cubre de más)" if 0 < d < 0.07 else
           "demasiado ancho" if d >= 0.07 else "algo estrecho (cubre de menos)" if d > -0.07 else "demasiado estrecho")
    franja = ("más de 95 %" if c >= 0.95 else "85-95 %" if c >= 0.85 else "70-85 %" if c >= 0.7
              else "50-70 %" if c >= 0.5 else "menos de la mitad")
    return f"{txt}: {franja} de los/las {unidad} reales quedan dentro".replace("los/las horas", "las horas").replace("los/las días", "los días")


def dispersion(d: float) -> str:
    if pd.isna(d):
        return "sin dato"
    return ("parecida a Poisson (varianza ≈ media)" if d < 1.2 else
            "algo de sobredispersión (varianza 1.2 a 2 veces la media)" if d < 2 else
            "sobredispersión fuerte (varianza más de 2 veces la media)")


def tendencia(mult: float) -> str:
    if pd.isna(mult):
        return "sin dato"
    p = (mult - 1) * 100
    a, s = abs(p), "sube" if p > 0 else "baja"
    return ("estable (menos de 2 % al año)" if a < 2 else f"{s} algo (2-5 % al año)" if a < 5
            else f"{s} bastante (5-15 % al año)" if a < 15 else f"{s} mucho (más de 15 % al año)")


def main(argv: list[str] | None = None) -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=None)
    a = ap.parse_args(argv)
    sal = carpeta_salida(a.salida)
    pb = sal / "powerbi"
    if not (sal / "meta.json").exists():
        print("No encontré la corrida; corre primero python -m pronostico.")
        return 1
    meta = json.loads((sal / "meta.json").read_text(encoding="utf-8"))
    met = pd.read_csv(pb / "metricas_modelos.csv")
    efe = pd.read_csv(pb / "efectos_calendario.csv")
    per = pd.read_csv(pb / "perfil_semana.csv")
    nivel = meta["nivel_intervalo"]

    print("RESUMEN SEGURO DEL PRONÓSTICO (solo palabras y franjas)\n")
    for serie, info in meta["series"].items():
        print(f"== Serie: {serie} ==")
        print(f"- Distribución de los conteos por hora: {dispersion(info['dispersion'])}; "
              f"intervalos con {info['distribucion']}.")
        print(f"- Backtest: {info['semanas_backtest']} semanas de prueba, una a la vez, entrenando solo con lo anterior.")
        m = met[met["serie"] == serie].set_index("modelo")
        for mod in ("glm", "glm_nivel"):
            if mod not in m.index:
                continue
            g = m.loc[mod]
            nom = NOMBRES[mod]
            print(f"- [{nom}]")
            for base in ("naive_semanal", "promedio_semanal"):
                if base in m.index:
                    print(f"    frente a {NOMBRES[base]}: error por hora {comparar(g['mae_hora'], m.loc[base, 'mae_hora'])}, "
                          f"error por día {comparar(g['mae_dia'], m.loc[base, 'mae_dia'])}.")
            print(f"    frente a la naive (MASE): por hora {mejora(g['mase_hora'])}; por día {mejora(g['mase_dia'])}.")
            print(f"    error típico: por hora {pct(g['mae_hora'] / g['media_real_hora'])} de la llegada media por hora; "
                  f"por día {pct(g['mape_dia'])} (MAPE diario).")
            ses = g["sesgo_hora"] / g["media_real_hora"] if g["media_real_hora"] else float("nan")
            print("    sesgo: " + ("sin sesgo apreciable" if abs(ses) < 0.03 else
                                   ("tiende a quedarse corto (subestima) " if ses > 0 else "tiende a pasarse (sobreestima) ")
                                   + pct(ses)) + ".")
            print(f"    intervalo del {int(nivel * 100)} % por día (calibrado fuera de muestra): "
                  f"{cobertura(g.get('cobertura_intervalo_dia'), nivel, 'días')}.")
            print(f"    intervalo del {int(nivel * 100)} % por hora: {cobertura(g['cobertura_intervalo'], nivel)}.")
        if "promedio_semanal" in m.index:
            b = m.loc["promedio_semanal"]
            print(f"- Línea base 'promedio 4 semanas' (referencia): MAPE diario {pct(b['mape_dia'])}; "
                  f"intervalo diario {cobertura(b.get('cobertura_intervalo_dia'), nivel, 'días')}.")
        mejor = m["mae_dia"].idxmin()
        print(f"- Mejor modelo por error diario (de los cuatro): {NOMBRES.get(mejor, mejor)}.")
        el = info.get("modelo_elegido")
        if el:
            print(f"- Modelo usado para el pronóstico futuro (el mejor de los que usan calendario): {NOMBRES.get(el, el)}.")
            if el == "glm_nivel":
                print(f"- Ajuste de nivel reciente: las últimas 4 semanas estuvieron "
                      f"{comparar(info.get('factor_nivel', 1.0), 1.0)} frente a lo que esperaba el GLM.")
        e = efe[efe["serie"] == serie].set_index("efecto")["multiplicador"]
        for k, nombre in EFECTOS.items():
            if k in e:
                print(f"- Llegadas en {nombre} frente a un día comparable: {comparar(e[k], 1.0)}.")
        if "tendencia_por_anio" in e:
            print(f"- Tendencia de fondo: {tendencia(e['tendencia_por_anio'])}.")
        p = per[per["serie"] == serie]
        if len(p):
            top = p.nlargest(3, "relativo")
            bot = p.nsmallest(1, "relativo").iloc[0]
            picos = "; ".join(f"{DIAS[int(r.dia_semana)]} {int(r.hora_dia):02d}h" for r in top.itertuples())
            print(f"- Horas más cargadas de la semana según el modelo: {picos}.")
            print(f"- Hora más tranquila: {DIAS[int(bot.dia_semana)]} {int(bot.hora_dia):02d}h; "
                  f"la hora pico es {comparar(top['relativo'].iloc[0], bot['relativo'])} que esa.")
            por_dia = p.groupby("dia_semana")["relativo"].mean()
            print(f"- Día más cargado: {DIAS[int(por_dia.idxmax())]}; más tranquilo: {DIAS[int(por_dia.idxmin())]} "
                  f"({comparar(por_dia.max(), por_dia.min())}).")
        print()
    print("Tablas para Power BI (quedan en tu computador, no se comparten):")
    for f in sorted(pb.glob("*.csv")):
        print(f"  {f.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
