"""Resumen seguro del reporte de series: SOLO palabras, franjas y comparaciones cualitativas
("fuerte", "sube algo", "entre 1.5 y 3 veces", "15h-18h"). Sin conteos, sin fechas, sin valores.
Es lo único que se puede compartir con Claude.

Uso:  python -m series_tiempo.resumen_seguro [--salida <carpeta>]
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from Cuellos_botella.resumen_seguro import cuanto, es

from . import datos

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]


def comparar(a: float, b: float) -> str:
    """'parecido', 'algo mayor (1.25 a 1.5 veces)', 'menor (0.5 a 0.8 veces)'… sin preposición."""
    if pd.isna(a) or pd.isna(b) or b <= 0:
        return "no comparable"
    r = a / b
    for lim, txt in [(0.5, "mucho menor (menos de la mitad)"), (0.8, "menor (0.5 a 0.8 veces)"),
                     (0.95, "algo menor (0.8 a 0.95 veces)"), (1.05, "parecido"), (1.25, "algo mayor (1.05 a 1.25 veces)"),
                     (1.5, "mayor (1.25 a 1.5 veces)"), (3, "bastante mayor (1.5 a 3 veces)")]:
        if r < lim:
            return txt
    return "mucho mayor (más de 3 veces)"


def fuerza(x: float) -> str:
    if pd.isna(x):
        return "sin dato"
    return "débil" if x < 0.3 else "moderada" if x < 0.6 else "fuerte"


def correlacion(r: float) -> str:
    if pd.isna(r):
        return "sin dato"
    a = abs(r)
    sentido = "" if a < 0.1 else (" positiva" if r > 0 else " negativa")
    return ("casi nula" if a < 0.1 else "débil" if a < 0.3 else "moderada" if a < 0.5 else "fuerte") + sentido


def pendiente(p: float) -> str:
    if pd.isna(p):
        return "sin dato"
    a, s = abs(p), "sube" if p > 0 else "baja"
    return ("estable (menos de 2 % al año)" if a < 2 else f"{s} algo (2-5 % al año)" if a < 5
            else f"{s} bastante (5-15 % al año)" if a < 15 else f"{s} mucho (más de 15 % al año)")


def largo(dias: int) -> str:
    return ("menos de 6 meses" if dias < 182 else "entre 6 meses y un año" if dias < 365
            else "entre uno y dos años" if dias < 730 else "más de dos años")


def lista_horas(h: list[int]) -> str:
    return ", ".join(f"{x:02d}h" for x in sorted(h))


def main(argv: list[str] | None = None) -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=None)
    a = ap.parse_args(argv)
    sal = datos.carpeta_salida(a.salida)
    tab = sal / "tablas"
    if not (sal / "datos" / "series_diarias.parquet").exists():
        print("No encontré la corrida; corre primero python -m series_tiempo.")
        return 1

    def t(nombre):
        p = tab / f"{nombre}.csv"
        return pd.read_csv(p) if p.exists() else None

    s = datos.cargar(sal)
    d = s["dias"]
    ok = d[d["completo"].astype(bool)]
    h = s["horas"][s["horas"]["completo"].astype(bool)]

    print("\n== A · Cobertura ==")
    inc = sorted(set(d.index[~d["completo"].astype(bool)].to_period("M")))
    meses = sorted(set(d.index.to_period("M")))
    if inc:
        donde = [x for x, c in (("al inicio", meses[0] in inc), ("al final", meses[-1] in inc),
                                ("en medio del periodo", any(m in inc for m in meses[1:-1]))) if c]
        print(f"  meses con días excluidos: {'uno' if len(inc) == 1 else 'varios'}, {' y '.join(donde)}")
    print(f"  tramo continuo de días completos: {largo(int(datos.tramo_continuo(d['completo'].astype(bool)).sum()))}")
    print(f"  horas sin ninguna llegada: {cuanto((h['llegadas'] == 0).mean())}")

    print("\n== B · Tendencia ==")
    c = d[datos.tramo_continuo(d["completo"].astype(bool))]["llegadas"].astype(float)
    if len(c) > 60:
        tt = np.arange(len(c)) / 365.25
        b = np.polyfit(tt, c.to_numpy(), 1)[0]
        print(f"  nivel: {pendiente(100 * b / c.mean())}")
    anios = ok.groupby(ok.index.year)["llegadas"].mean()
    if len(anios) >= 2:
        print(f"  último año frente al primero: {comparar(anios.iloc[-1], anios.iloc[0])}")

    print("\n== C · Dentro del día ==")
    p = t("perfil_hora")
    if p is not None:
        m = p["media"]
        alto = m > m.quantile(0.75)
        print(f"  horas más cargadas: {lista_horas(p.loc[alto, 'hora'].tolist())}")
        print(f"  horas más tranquilas: {lista_horas(p.loc[m < m.quantile(0.25), 'hora'].tolist())}")
        print(f"  la hora pico {es(m.max(), m.min())} la más tranquila")
    dw = h.groupby([h.index.dayofweek, h.index.hour])["llegadas"].mean().unstack()
    if len(dw) == 7:
        forma = dw.div(dw.sum(axis=1), axis=0)
        dif = (forma.max() - forma.min()).max() / forma.to_numpy().mean()
        print("  forma del día entre días de la semana: " + ("parecida" if dif < 0.5 else "algo distinta" if dif < 1
                                                            else "bastante distinta"))

    print("\n== D · Semana ==")
    w = t("dia_semana")
    if w is not None:
        print(f"  día más cargado: {DIAS[int(w.loc[w['mean'].idxmax(), 'dia_semana'])]}; más liviano: "
              f"{DIAS[int(w.loc[w['mean'].idxmin(), 'dia_semana'])]}; el más cargado {es(w['mean'].max(), w['mean'].min())} el más liviano")

    print("\n== E · Año ==")
    m = t("mes")
    if m is not None and m["media"].notna().sum() >= 2:
        mm = m.dropna(subset=["media"])
        print(f"  años con días completos: {'uno' if ok.index.year.nunique() == 1 else 'dos' if ok.index.year.nunique() == 2 else 'tres o más'}")
        print(f"  mes más cargado: {MESES[int(mm.loc[mm['media'].idxmax(), 'mes']) - 1]}; más liviano: "
              f"{MESES[int(mm.loc[mm['media'].idxmin(), 'mes']) - 1]}; el más cargado {es(mm['media'].max(), mm['media'].min())} el más liviano")

    print("\n== F · Festivos y temporadas (llegadas frente a un día normal del mismo mes y día de la semana) ==")
    f = t("efecto_calendario")
    if f is not None:
        for _, r in f.iterrows():
            pocos = " (muy pocos días, poco confiable)" if r["dias"] < 5 else ""
            if r["dias"] > 0:
                print(f"  {r['categoria']}: {comparar(r['razon_mediana'], 1.0)}{pocos}")

    print("\n== G · Descomposición ==")
    fz = t("fuerza_componentes")
    if fz is not None:
        for _, r in fz.iterrows():
            print(f"  serie {r['serie']}, {r['componente']}: {fuerza(r['fuerza'])}")
    at = t("dias_atipicos")
    if at is not None:
        n = len(at)
        print(f"  días atípicos (resto > 3 desviaciones): {'ninguno' if n == 0 else 'unos pocos' if n <= 5 else 'varios' if n <= 20 else 'muchos'}")
        if n:
            print(f"    en qué meses caen: {', '.join(sorted({MESES[int(x[5:7]) - 1] for x in at['fecha']}))}")

    print("\n== H · Autocorrelación ==")
    lb = t("ljung_box_resto")
    if lb is not None:
        queda = (lb["p_valor"] < 0.05).any()
        print("  después de quitar tendencia y ciclo semanal " + ("todavía queda autocorrelación (hay información "
              "para un modelo ARMA)" if queda else "el resto ya parece ruido"))

    print("\n== I · Estacionariedad (ADF + KPSS, serie diaria) ==")
    e = t("pruebas_estacionariedad")
    if e is not None:
        for _, r in e.iterrows():
            print(f"  {r['serie']}: {r['lectura']}")

    print("\n== J · Distribución ==")
    g = h.groupby([h.index.dayofweek, h.index.hour])["llegadas"].agg(["mean", "var"])
    disp = float((g["var"] / g["mean"]).replace([np.inf, -np.inf], np.nan).mean())
    print("  varianza frente a media por franja: " + ("cerca de 1 (Poisson)" if disp < 1.2 else
          "algo de sobredispersión (1.2-1.5)" if disp < 1.5 else "sobredispersión clara (más de 1.5)"))
    ceros_obs, ceros_esp = (h["llegadas"] == 0).mean(), float(np.mean(np.exp(-g["mean"].to_numpy())))
    print(f"  horas con 0 llegadas, observado frente a lo esperado por Poisson: {comparar(ceros_obs, ceros_esp)}")
    di = t("dispersion")
    if di is not None and (di["indicador"] == "lambda de Box-Cox de las llegadas diarias").any():
        lam = float(di.loc[di["indicador"] == "lambda de Box-Cox de las llegadas diarias", "valor"].iloc[0])
        print("  transformación sugerida para la serie diaria: " + ("ninguna (lambda cerca de 1)" if lam > 0.75 else
              "raíz (lambda cerca de 0.5)" if lam > 0.25 else "logaritmo (lambda cerca de 0)" if lam > -0.25 else
              "otra (lambda negativo: revisar)"))

    print("\n== K · Otras series del flujo ==")
    cc = t("correlacion_cruzada")
    if cc is not None:
        for par, cz in cc.groupby("par"):
            if cz["correlacion"].isna().all():
                print(f"  {par}: sin dato (alguna de las series no varía)")
                continue
            k = cz.loc[cz["correlacion"].abs().idxmax()]
            cuando = "0 h (misma hora)" if k["desfase_h"] == 0 else "%d h" % int(k["desfase_h"])
            print(f"  {par}: correlación {correlacion(k['correlacion'])}, más alta a las {cuando}")
    pm = t("proporciones_mensuales")
    if pm is not None and len(pm):
        for col, nombre in (("proporcion_hospitalizada", "se hospitalizan"), ("proporcion_contacto_breve", "son contactos breves")):
            v = pm[col].dropna()
            if len(v):
                print(f"  de las llegadas {nombre}: {cuanto(v.median())}; entre meses, el máximo {es(v.max(), v.min())} el mínimo")

    print("\n== L · Por grupo ==")
    gr = t("grupos")
    if gr is not None:
        for _, r in gr.iterrows():
            print(f"  {r['dimension']} {r['grupo']}: {cuanto(r['proporcion'])} de las llegadas")

    print("\n== M · Tiempos en urgencias ==")
    cg = t("congestion")
    if cg is not None:
        for _, r in cg.iterrows():
            print(f"  {r['destino']}: relación entre llegadas de la semana y mediana de espera {correlacion(r['spearman_llegadas_vs_mediana'])}")
    err = sal / "errores.log"
    if err.exists() and err.stat().st_size:
        print("\n  (hubo secciones que no se generaron; el detalle está en errores.log: compárteme solo el tipo de error)")
    print("\nTodo lo de arriba se puede compartir: palabras, franjas y comparaciones cualitativas.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
