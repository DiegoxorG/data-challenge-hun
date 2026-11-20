"""Uso:
    python -m semaforo [--pronostico <carpeta>] [--salida <carpeta>]

Lee lo que deja `python -m pronostico` (DATA_DIR/pronostico) y escribe en DATA_DIR/semaforo (nunca en el repo):
  powerbi/semaforo_futuro.csv        un turno por fila: pronóstico, intervalo, probabilidades, color y acción
  powerbi/semaforo_validacion.csv    el semáforo aplicado a las semanas del backtest (modelo y naïve) vs lo real
  powerbi/semaforo_metricas.csv      sensibilidad, precisión, críticos en verde, tasa de alerta (modelo y naïve)
  powerbi/semaforo_confusion.csv     color pronosticado × categoría real
  powerbi/umbrales.csv               percentiles por turno que definen cargado / crítico
  powerbi/protocolo.csv              qué hacer con cada color y quién
  meta.json
No se conecta a la base. En consola solo imprime avance, sin cifras de los datos.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from . import calculo as S

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def carpeta(ruta, defecto: str, nombre: str) -> Path:
    from hun.config import validar_carpeta
    if ruta is None:
        from hun.config import data_dir
        d = data_dir() / defecto
    else:
        d = Path(ruta)
    return validar_carpeta(d, nombre)


def correr(pron: Path, salida: Path, log=print) -> dict:
    pb_in, pb = pron / "powerbi", salida / "powerbi"
    pb.mkdir(parents=True, exist_ok=True)
    meta_p = json.loads((pron / "meta.json").read_text(encoding="utf-8"))
    ph = pd.read_csv(pb_in / "pronostico_horario.csv", parse_dates=["hora"])
    bt = pd.read_csv(pb_in / "backtest_horario.csv", parse_dates=["hora", "corte"])
    futuros, vals, mets, confs, ums = [], [], [], [], []
    meta = {"turnos": {t: [min(h) if t != "noche" else 19, (max(h) + 1) if t != "noche" else 7] for t, h in S.TURNOS.items()},
            "percentiles": [S.P_CARGADO, S.P_CRITICO], "semanas_referencia": S.SEMANAS_REFERENCIA,
            "reglas": {"rojo": f"P(crítico) >= {S.UMBRAL_ROJO}",
                       "amarillo": f"P(cargado) >= {S.UMBRAL_AMARILLO_CARGADO} o P(crítico) >= {S.UMBRAL_AMARILLO_CRITICO}"},
            "series": {}}
    for serie, info in meta_p["series"].items():
        el = info.get("modelo_elegido", "glm")
        log(f"· {serie}: umbrales, validación ({el} y naïve) y semáforo futuro")
        h = ph[(ph["serie"] == serie) & (ph["tipo"] == "historico")][["hora", "real"]]
        hist = S.por_turno(h, ["real"])
        b = bt[bt["serie"] == serie]
        for mod in (el, "naive_semanal"):
            v = S.validar(b, hist, mod)
            if v.empty:
                continue
            v.insert(0, "serie", serie)
            vals.append(v)
            m = S.metricas_semaforo(v)
            mets.append({"serie": serie, "modelo": mod, "es_elegido": mod == el, **m})
            c = S.matriz_confusion(v)
            c.insert(0, "modelo", mod)
            c.insert(0, "serie", serie)
            confs.append(c)
        # Futuro: umbrales con las últimas 52 semanas y dispersión con todo el backtest del modelo elegido
        tb = S.por_turno(b[b["modelo"] == el], ["real", "pred"], ["corte"])
        a = S.alpha_turno(tb["real"], tb["pred"])
        u = S.umbrales(hist)
        u.insert(0, "serie", serie)
        ums.append(u)
        f = S.por_turno(ph[(ph["serie"] == serie) & (ph["tipo"] == "futuro")][["hora", "pred"]], ["pred"])
        f = S.aplicar(f, u, a)
        f.insert(0, "serie", serie)
        f["dia_nombre"] = f["dia_semana"].map(lambda i: DIAS[int(i)])
        f["orden_turno"] = f["turno"].map({t: i for i, t in enumerate(S.ORDEN_TURNOS)})
        futuros.append(f)
        meta["series"][serie] = {"modelo": el, "alpha_turno": a}
    if not futuros:
        raise RuntimeError("No hay series en la corrida del pronóstico.")
    fut = pd.concat(futuros, ignore_index=True).merge(S.protocolo(), on=["serie", "color"], how="left")
    fut.sort_values(["serie", "fecha", "orden_turno"]).to_csv(pb / "semaforo_futuro.csv", index=False)
    pd.concat(vals, ignore_index=True).to_csv(pb / "semaforo_validacion.csv", index=False)
    pd.DataFrame(mets).to_csv(pb / "semaforo_metricas.csv", index=False)
    pd.concat(confs, ignore_index=True).to_csv(pb / "semaforo_confusion.csv", index=False)
    pd.concat(ums, ignore_index=True).to_csv(pb / "umbrales.csv", index=False)
    S.protocolo().to_csv(pb / "protocolo.csv", index=False)
    (salida / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m semaforo", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pronostico", default=None, help="carpeta de python -m pronostico (por defecto DATA_DIR/pronostico)")
    ap.add_argument("--salida", default=None, help="carpeta de salida (por defecto DATA_DIR/semaforo)")
    a = ap.parse_args(argv)
    pron = carpeta(a.pronostico, "pronostico", "El pronóstico")
    if not (pron / "meta.json").exists():
        print("No encontré la corrida del pronóstico; corre primero python -m pronostico.")
        return 1
    sal = carpeta(a.salida, "semaforo", "La salida")
    print(f"Salida: {sal}")
    correr(pron, sal)
    print(f"Listo. Tablas para Power BI en: {sal / 'powerbi'}")
    print("Para compartir con Claude usa SOLO: python -m semaforo.resumen_seguro")
    return 0


if __name__ == "__main__":
    sys.exit(main())
