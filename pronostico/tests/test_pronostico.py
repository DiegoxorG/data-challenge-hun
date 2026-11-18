"""Tests del pronóstico con datos inventados dentro de cada test (sin base, sin DATA_DIR)."""
import json

import numpy as np
import pandas as pd
import pytest

from pronostico import modelo as M
from pronostico.__main__ import carpeta_salida, correr


def inventado(dias=420, semilla=0, efecto_festivo=0.7, tamano_nb=5.0):
    """Llegadas por hora con ciclo diario, lunes cargado, fin de semana tranquilo, festivos que
    bajan las llegadas y sobredispersión (binomial negativa con n = tamano_nb)."""
    rng = np.random.default_rng(semilla)
    h = pd.date_range("2023-01-02", periods=24 * dias, freq="h")
    d = pd.date_range(h[0].normalize(), h[-1].normalize() + pd.Timedelta(days=30), freq="D")
    cal = pd.DataFrame(False, index=d, columns=M.CALENDARIO)
    cal.loc[d[5::37], "festivo"] = True
    cal.loc[d[6::37], "despues_de_festivo"] = True
    perfil = 1 + 0.8 * np.sin(2 * np.pi * (h.hour - 8) / 24)
    semana = np.where(h.dayofweek == 0, 1.4, np.where(h.dayofweek >= 5, 0.8, 1.0))
    fest = cal["festivo"].reindex(h.normalize()).to_numpy()
    lam = 3 * perfil * semana * np.where(fest, efecto_festivo, 1.0)
    y = rng.negative_binomial(tamano_nb, tamano_nb / (tamano_nb + lam))
    horas = pd.DataFrame({"llegadas": y, "llegadas_hospitalizan": rng.binomial(y, 0.15)}, index=h)
    horas["completo"] = True
    horas.loc[horas.index[:7], "completo"] = False          # primer día cortado, como en el extracto real
    return horas, cal


def test_variables_forma_y_hora_de_la_semana():
    horas, cal = inventado(dias=14)
    X = M.variables(horas.index, cal, horas.index[0])
    assert X.filter(like="how_").sum(axis=1).eq(1).all()      # una sola hora de la semana activa
    assert X.shape[0] == len(horas)
    assert not X.isna().any().any()


def test_glm_recupera_festivo_y_dispersion():
    horas, cal = inventado()
    g = M.ajustar_glm(horas["llegadas"].astype(float), cal)
    e = M.efectos(g).set_index("efecto")["multiplicador"]
    assert 0.6 < e["festivo"] < 0.8                           # inventado: 0.7
    assert 0.9 < e["tendencia_por_anio"] < 1.1                # sin tendencia
    assert g.dispersion > 1.2 and 0.1 < g.alpha_nb < 0.35     # inventado: alpha = 1/5
    p = M.perfil_semana(g)
    assert p.groupby("dia_semana")["relativo"].mean().idxmax() == 0   # lunes


def test_backtest_glm_gana_a_la_naive_y_cubre():
    horas, cal = inventado()
    y = horas["llegadas"].astype(float).where(horas["completo"])
    bt = M.backtest(y, cal, semanas=4)
    assert bt["corte"].nunique() == 4
    assert (bt.groupby(["corte", "modelo"]).size() == M.H_SEMANA).all()
    # Ningún corte usa datos de su propia semana de prueba: el último dato de entrenamiento es anterior
    assert (bt["hora"] >= bt["corte"]).all()
    m = M.metricas(bt).set_index("modelo")
    assert m.loc["glm", "mase_hora"] < 0.9
    assert m.loc["glm", "mae_dia"] < m.loc["naive_semanal", "mae_dia"]
    assert 0.85 <= m.loc["glm", "cobertura_intervalo"] <= 0.99
    assert 0.7 <= m.loc["glm", "cobertura_intervalo_dia"] <= 1.0


def test_sin_tendencia_falsa_con_poco_mas_de_un_anio():
    horas, cal = inventado(dias=400, semilla=3)
    g = M.ajustar_glm(horas["llegadas"].astype(float), cal)
    assert not any(c.startswith("anual_") for c in g.columnas)      # < 2 años: sin estacionalidad anual
    assert 0.95 < M.efectos(g).set_index("efecto").loc["tendencia_por_anio", "multiplicador"] < 1.05


def test_poisson_sin_sobredispersion_usa_poisson():
    horas, cal = inventado(tamano_nb=1e6)                       # prácticamente Poisson
    g = M.ajustar_glm(horas["llegadas"].astype(float), cal)
    assert g.dispersion < 1.15
    li, ls = g.intervalo(np.array([3.0]))
    assert li[0] <= 3 <= ls[0]


def test_salida_dentro_del_repo_se_rechaza():
    from pathlib import Path
    with pytest.raises(RuntimeError):
        carpeta_salida(Path(__file__).resolve().parents[2] / "salida_prohibida")


def test_punta_a_punta_y_resumen_sin_cifras(tmp_path, capsys):
    horas, cal = inventado(dias=300)
    sal = carpeta_salida(tmp_path / "pron")
    meta = correr(horas, cal, sal, ["llegadas", "llegadas_hospitalizan", "no_existe"],
                  horizonte_dias=7, semanas_backtest=3, log=lambda *_: None)
    assert set(meta["series"]) == {"llegadas", "llegadas_hospitalizan"}
    pb = sal / "powerbi"
    for f in ["pronostico_horario", "pronostico_diario", "backtest_horario", "backtest_diario",
              "metricas_modelos", "efectos_calendario", "perfil_semana"]:
        assert (pb / f"{f}.csv").exists(), f
    ph = pd.read_csv(pb / "pronostico_horario.csv", parse_dates=["hora"])
    fut = ph[(ph["tipo"] == "futuro") & (ph["serie"] == "llegadas")]
    assert len(fut) == 24 * 7 and fut["real"].isna().all()
    assert (fut["li"] <= fut["pred"]).all() and (fut["pred"] <= fut["ls"]).all()
    assert fut["hora"].min() > ph.loc[ph["tipo"] == "historico", "hora"].max() - pd.Timedelta(hours=1)
    pdia = pd.read_csv(pb / "pronostico_diario.csv")
    assert pdia.loc[pdia["tipo"] == "futuro", "li"].notna().all()
    assert json.loads((sal / "meta.json").read_text(encoding="utf-8"))["horizonte_dias"] == 7

    from pronostico.resumen_seguro import main as resumen
    capsys.readouterr()
    assert resumen(["--salida", str(sal)]) == 0
    texto = capsys.readouterr().out
    assert "lunes" in texto and "festivo" in texto
    sueltos = [w for w in texto.replace("(", " ").replace(")", " ").split() if w.isdigit() and len(w) >= 3]
    assert not sueltos, sueltos
    # Los únicos decimales permitidos son los límites fijos de las franjas (0.5, 1.25, ...)
    franjas = {"0.5", "0.8", "0.95", "1.05", "1.25", "1.5", "1.2"}
    decimales = {w.strip("(),.:;") for w in texto.split() if "." in w.strip("(),.:;")
                 and w.strip("(),.:;").replace(".", "").isdigit()}
    assert decimales <= franjas, decimales
