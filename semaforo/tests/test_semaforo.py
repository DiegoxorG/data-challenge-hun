"""Tests del semáforo con datos inventados (sin base, sin DATA_DIR)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from semaforo import calculo as S

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pronostico" / "tests"))


def test_turnos_y_noche_del_dia_anterior():
    h = pd.DatetimeIndex(["2025-03-03 07:00", "2025-03-03 12:59", "2025-03-03 13:00", "2025-03-03 19:00",
                          "2025-03-04 06:00", "2025-03-04 07:00"])
    f, n = S.turno_de(h)
    assert list(n) == ["mañana", "mañana", "tarde", "noche", "noche", "mañana"]
    assert f[4] == pd.Timestamp("2025-03-03")            # la madrugada pertenece a la noche que empezó el día antes
    assert sum(S.HORAS_TURNO.values()) == 24


def test_por_turno_descarta_turnos_incompletos():
    h = pd.date_range("2025-03-03 10:00", periods=24, freq="h")   # hasta el 4 a las 9 h
    t = S.por_turno(pd.DataFrame({"hora": h, "real": 1.0}), ["real"])
    # mañanas del 3 (desde 10 h) y del 4 (hasta 9 h) incompletas; tarde y noche del 3 completas
    assert set(t["turno"]) == {"tarde", "noche"} and t.loc[t["turno"] == "noche", "real"].iloc[0] == 12


def test_reglas_de_color():
    assert list(S.colorear([0.1, 0.6, 0.3, 0.9, 0.3], [0.0, 0.1, 0.25, 0.45, 0.15])) == \
        ["verde", "amarillo", "amarillo", "rojo", "verde"]


def test_probabilidad_crece_con_la_media_y_baja_con_el_umbral():
    p = S.prob_supera([10, 20, 30], 0.05, [20, 20, 20])
    assert p[0] < p[1] < p[2]
    assert S.prob_supera([20], 0.05, [10])[0] > S.prob_supera([20], 0.05, [30])[0]


def _corridas(tmp_path):
    from test_pronostico import inventado
    from pronostico.__main__ import carpeta_salida, correr
    from semaforo.__main__ import correr as correr_s
    horas, cal = inventado(dias=520, semilla=2)
    pron = carpeta_salida(tmp_path / "pronostico")
    correr(horas, cal, pron, ["llegadas", "llegadas_hospitalizan"], horizonte_dias=14, semanas_backtest=8,
           log=lambda *_: None)
    sal = tmp_path / "semaforo"
    sal.mkdir()
    correr_s(pron, sal, log=lambda *_: None)
    return sal / "powerbi"


def test_punta_a_punta_validacion_y_futuro(tmp_path, capsys):
    pb = _corridas(tmp_path)
    fut = pd.read_csv(pb / "semaforo_futuro.csv")
    assert set(fut["color"]) <= set(S.COLORES)
    assert fut["accion"].notna().all() and fut["responsable"].notna().all()
    assert ((fut["p_critico"] <= fut["p_cargado"] + 1e-12)).all()      # crítico implica cargado
    assert len(fut[fut["serie"] == "llegadas"]) >= 3 * 13                # ~14 días × 3 turnos (bordes incompletos fuera)
    met = pd.read_csv(pb / "semaforo_metricas.csv")
    assert set(met["modelo"]) >= {"naive_semanal"} and met["es_elegido"].any()
    el = met[(met["serie"] == "llegadas") & met["es_elegido"]].iloc[0]
    # Los datos inventados tienen lunes cargados sistemáticamente: el semáforo debe anticiparlos
    assert el["turnos_criticos"] > 0
    assert el["sensibilidad_critico"] >= 0.5 and el["criticos_en_verde"] <= 0.5
    assert 0 < el["tasa_alerta"] < 0.8                                   # no todo es alerta
    assert el["riesgo_critico_en_alerta"] > el["riesgo_critico_en_verde"]  # la alerta concentra el riesgo
    conf = pd.read_csv(pb / "semaforo_confusion.csv")
    assert conf.groupby(["serie", "modelo"])["turnos"].sum().gt(0).all()
    u = pd.read_csv(pb / "umbrales.csv")
    assert (u["umbral_critico"] >= u["umbral_cargado"]).all()

    from semaforo.resumen_seguro import main
    capsys.readouterr()
    assert main(["--salida", str(pb.parent)]) == 0
    t = capsys.readouterr().out
    assert "turnos críticos anticipados" in t
    assert not [w for w in t.replace("(", " ").split() if w.isdigit() and len(w) >= 3]


def test_umbrales_sin_mirar_el_futuro():
    h = pd.date_range("2024-01-01", periods=24 * 400, freq="h")
    y = np.where(h < pd.Timestamp("2024-12-01"), 1.0, 100.0)            # después del corte, todo enorme
    hist = S.por_turno(pd.DataFrame({"hora": h, "real": y}), ["real"])
    u = S.umbrales(hist, hasta=pd.Timestamp("2024-12-01"))
    assert (u["umbral_critico"] < 100).all()                            # no se filtró información del periodo evaluado
