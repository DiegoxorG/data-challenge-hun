"""Uso:
    python -m pronostico [--salida <carpeta>] [--series-dir <carpeta>] [--horizonte-dias 14]
                         [--semanas-backtest 12] [--series llegadas llegadas_hospitalizan]

Lee las series que deja `python -m series_tiempo` (DATA_DIR/series_tiempo), entrena los modelos de
pronostico/modelo.py, los evalúa con backtest rodante y pronostica los próximos días. Escribe en
DATA_DIR/pronostico (nunca en el repo):
  powerbi/*.csv     tablas listas para Power BI (ver README)
  meta.json         parámetros y diagnóstico del modelo (lo lee el resumen seguro)
No se conecta a la base. En consola solo imprime avance, sin cifras de los datos.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import modelo as M

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SERIES_DEFECTO = ["llegadas", "llegadas_hospitalizan"]
CARPETA_DEFECTO = "pronostico"


def carpeta_salida(ruta: str | Path | None) -> Path:
    """Por defecto DATA_DIR/pronostico. Nunca dentro del repo ni en una carpeta en la nube."""
    from hun.config import validar_carpeta
    if ruta is None:
        from hun.config import data_dir
        d = data_dir() / CARPETA_DEFECTO
    else:
        d = Path(ruta)
    d = validar_carpeta(d, "La salida")
    (d / "powerbi").mkdir(parents=True, exist_ok=True)
    return d


def cargar_series(series_dir: str | Path | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    from series_tiempo import cargar
    s = cargar(series_dir)
    return s["horas"], s["dias"]


def calendario_completo(dias: pd.DataFrame, hasta: pd.Timestamp) -> pd.DataFrame:
    """Calendario de la historia (ya viene en las series diarias) + el de los días futuros."""
    from series_tiempo import calendario
    cal = calendario.tabla(dias.index.min(), hasta)
    return cal[M.CALENDARIO]


def correr(horas: pd.DataFrame, cal: pd.DataFrame, salida: Path, series: list[str],
           horizonte_dias: int = 14, semanas_backtest: int = 12, log=print) -> dict:
    """Todo el proceso sobre series ya cargadas. Devuelve meta (lo mismo que meta.json)."""
    pb = salida / "powerbi"
    completo = horas["completo"].fillna(False).astype(bool)
    hist, bts, mets, efs, perfiles, diarios = [], [], [], [], [], []
    meta = {"horizonte_dias": horizonte_dias, "semanas_backtest_pedidas": semanas_backtest,
            "nivel_intervalo": M.NIVEL_INTERVALO, "series": {}}
    for serie in series:
        if serie not in horas:
            log(f"  ! no existe la serie '{serie}' en las series horarias; se salta")
            continue
        y = horas[serie].astype(float).where(completo)
        if y.notna().sum() < 24 * 7 * 30:
            log(f"  ! '{serie}' tiene muy poca historia válida; se salta")
            continue
        log(f"· {serie}: backtest rodante")
        bt = M.backtest(y, cal, semanas_backtest)
        bt.insert(0, "serie", serie)
        bts.append(bt)
        m = M.metricas(bt)
        m.insert(0, "serie", serie)
        mets.append(m)

        log(f"· {serie}: modelo final y pronóstico")
        ultimo = y.dropna().index.max()
        futuras = pd.date_range(ultimo + pd.Timedelta(hours=1), periods=24 * horizonte_dias, freq="h")
        fut, g = M.pronosticar(y, cal, futuras)
        ajuste = g.media(y.dropna().index, cal)
        h = pd.DataFrame({"hora": y.index, "real": y.to_numpy(), "pred": np.nan, "li": np.nan, "ls": np.nan})
        h.loc[y.notna().to_numpy(), "pred"] = ajuste
        h["tipo"] = "historico"
        fut["real"] = np.nan
        fut["tipo"] = "futuro"
        hs = pd.concat([h, fut[h.columns]], ignore_index=True)
        hs.insert(0, "serie", serie)
        hist.append(hs)

        # Diario: histórico (real vs ajuste) + futuro con su intervalo diario
        d = M.a_diario(hs[["serie", "tipo", "hora", "real", "pred"]])
        dfut = d["tipo"] == "futuro"
        li, ls = M.intervalo_diario(d.loc[dfut, "pred"].to_numpy(), g)
        d["li"], d["ls"] = np.nan, np.nan
        d.loc[dfut, "li"], d.loc[dfut, "ls"] = li, ls
        diarios.append(d)

        e = M.efectos(g)
        e.insert(0, "serie", serie)
        efs.append(e)
        p = M.perfil_semana(g)
        p.insert(0, "serie", serie)
        perfiles.append(p)
        meta["series"][serie] = {"dispersion": g.dispersion, "alpha_nb": g.alpha_nb,
                                 "distribucion": "binomial negativa" if g.alpha_nb > 1e-6 else "Poisson",
                                 "semanas_backtest": int(bt["corte"].nunique()) if len(bt) else 0,
                                 "n_variables": len(g.columnas)}

    if not hist:
        raise RuntimeError("No se pudo modelar ninguna serie.")

    def _horas(df):
        df = df.copy()
        df["fecha"] = df["hora"].dt.normalize()
        df["dia_semana"] = df["hora"].dt.dayofweek          # 0 = lunes
        df["hora_dia"] = df["hora"].dt.hour
        return df

    _horas(pd.concat(hist, ignore_index=True)).to_csv(pb / "pronostico_horario.csv", index=False)
    pd.concat(diarios, ignore_index=True).to_csv(pb / "pronostico_diario.csv", index=False)
    bt_all = pd.concat(bts, ignore_index=True)
    _horas(bt_all).to_csv(pb / "backtest_horario.csv", index=False)
    M.a_diario(bt_all[["serie", "modelo", "corte", "hora", "real", "pred"]]).to_csv(pb / "backtest_diario.csv", index=False)
    pd.concat(mets, ignore_index=True).to_csv(pb / "metricas_modelos.csv", index=False)
    pd.concat(efs, ignore_index=True).to_csv(pb / "efectos_calendario.csv", index=False)
    pd.concat(perfiles, ignore_index=True).to_csv(pb / "perfil_semana.csv", index=False)
    (salida / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pronostico", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", default=None, help="carpeta de salida (por defecto DATA_DIR/pronostico)")
    ap.add_argument("--series-dir", default=None, help="carpeta de series_tiempo (por defecto DATA_DIR/series_tiempo)")
    ap.add_argument("--horizonte-dias", type=int, default=14)
    ap.add_argument("--semanas-backtest", type=int, default=12)
    ap.add_argument("--series", nargs="+", default=SERIES_DEFECTO)
    a = ap.parse_args(argv)

    t0 = time.time()
    salida = carpeta_salida(a.salida)
    print(f"Salida: {salida}")
    print("· cargando las series de series_tiempo")
    horas, dias = cargar_series(a.series_dir)
    ultimo = horas.index[horas["completo"].fillna(False).astype(bool).to_numpy()].max()
    cal = calendario_completo(dias, ultimo + pd.Timedelta(days=a.horizonte_dias + 1))
    correr(horas, cal, salida, a.series, a.horizonte_dias, a.semanas_backtest)
    print(f"\nListo en {time.time() - t0:.0f} s. Tablas para Power BI en: {salida / 'powerbi'}")
    print("Para compartir con Claude usa SOLO: python -m pronostico.resumen_seguro")
    return 0


if __name__ == "__main__":
    sys.exit(main())
