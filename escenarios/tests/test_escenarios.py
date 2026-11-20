"""Tests de escenarios con datos inventados."""
import numpy as np
import pandas as pd
import pytest

from escenarios import calculo as C
from escenarios.__main__ import carpeta_salida, correr


def inventado(dias=120, semilla=0):
    rng = np.random.default_rng(semilla)
    h = pd.date_range("2024-01-01", periods=24 * dias, freq="h")
    ing = rng.poisson(np.where((h.hour >= 12) & (h.hour <= 18), 2.0, 0.5))
    alt = rng.poisson(np.where((h.hour >= 13) & (h.hour <= 18), 3.0, 0.3))
    df = pd.DataFrame({"ingresos_desde_urgencias": ing, "altas_cama": alt,
                       "censo_urgencias": 20 + rng.poisson(10, len(h)),
                       "censo_hospitalizacion": 60 + rng.poisson(5, len(h))}, index=h)
    df["completo"] = True
    return df


def test_ley_de_little_promedio():
    horas = inventado()
    p = C.perfil(horas, horas["completo"])
    e = C.espera_cama(p)
    tasa = p["ingresos_desde_urgencias"].mean()
    for h in (2, 4, 6):
        red = e[e["reduccion_espera_h"] == h]["reduccion_censo"].mean()
        assert red == pytest.approx(tasa * h, rel=1e-6)          # Little: tasa × horas
    assert (e[e["reduccion_espera_h"] == 0]["reduccion_censo"] == 0).all()


def test_suma_siguientes_circular():
    x = np.arange(C.H_SEMANA, dtype=float)
    s = C._suma_siguientes(x, 2)
    assert s[0] == 1 + 2 and s[-1] == 0 + 1                       # domingo 23 h → lunes 0 h y 1 h


def test_altas_temprano_libera_camas_en_la_manana():
    horas = inventado()
    a = C.altas_temprano(C.perfil(horas, horas["completo"]))
    m = a[(a["adelanto_h"] == 4) & (a["fraccion_altas"] == 0.5)].groupby("hora_dia")["camas_liberadas"].mean()
    assert m.loc[10] > m.loc[3] and m.loc[3] == 0                  # libera antes de la tarde, no en la madrugada
    assert (a[a["fraccion_altas"] == 0]["camas_liberadas"] == 0).all()


def test_punta_a_punta_y_resumen(tmp_path, capsys):
    sal = carpeta_salida(tmp_path / "esc")
    correr(inventado(), sal, excluir_ultimas_semanas=2)
    for f in ["escenario_espera_cama", "escenario_altas_temprano", "resumen_espera_cama"]:
        assert (sal / "powerbi" / f"{f}.csv").exists()
    from escenarios.resumen_seguro import main
    capsys.readouterr()
    assert main(["--salida", str(sal)]) == 0
    t = capsys.readouterr().out
    assert "Escenario 1" in t and not [w for w in t.split() if w.isdigit() and len(w) >= 3]


def test_salida_en_repo_rechazada():
    from pathlib import Path
    with pytest.raises(RuntimeError):
        carpeta_salida(Path(__file__).resolve().parents[2] / "x")
