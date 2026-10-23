import numpy as np
import pandas as pd

from Cuellos_botella.censo import Barrido, censo_horario


def test_censo_instantaneo_y_medio_casos_simples():
    b = Barrido(np.array([0.0, 5.0, 20.0]), np.array([10.0, 15.0, 20.0]))
    # [inicio, fin): un intervalo de duración 0 nunca cuenta
    assert list(b.censo(np.array([0, 5, 10, 15, 20]))) == [1, 2, 1, 0, 0]
    # Quien empieza justo en t no se cuenta al "llegar"
    assert b.censo(np.array([5.0]), excluir_inicio_en_t=True)[0] == 1
    # Promedio ponderado por tiempo: [0,10) acumula 10 + 5 = 15 -> 1.5 ; [10,20) acumula 5 -> 0.5
    assert np.allclose(b.censo_medio(np.array([0.0, 10.0]), 10.0), [1.5, 0.5])


def test_barrido_igual_a_fuerza_bruta():
    rng = np.random.default_rng(1)
    s = rng.uniform(0, 1000, 300)
    e = s + rng.exponential(50, 300)
    b = Barrido(s, e, origen=0.0)
    t = np.arange(0, 1100, 10.0)
    bruto_inst = np.array([((s <= x) & (e > x)).sum() for x in t])
    bruto_medio = np.array([np.clip(np.minimum(e, x + 10) - np.maximum(s, x), 0, None).sum() / 10 for x in t])
    assert np.array_equal(b.censo(t), bruto_inst)
    assert np.allclose(b.censo_medio(t, 10.0), bruto_medio)


def test_censo_horario_por_zona():
    est = pd.DataFrame({
        "zona": ["a", "a", "b"],
        "inicio": pd.to_datetime(["2020-01-01 00:00", "2020-01-01 00:30", "2020-01-01 01:00"]),
        "fin": pd.to_datetime(["2020-01-01 02:00", "2020-01-01 01:00", "2020-01-01 01:30"]),
    })
    cen, _ = censo_horario(est, ["a", "b"], est["inicio"].min(), pd.Timestamp("2020-01-01 01:00"))
    a = cen[cen["zona"] == "a"].set_index("hora")
    b = cen[cen["zona"] == "b"].set_index("hora")
    h0, h1 = pd.Timestamp("2020-01-01 00:00"), pd.Timestamp("2020-01-01 01:00")
    assert a.loc[h0, "censo_inst"] == 1 and a.loc[h1, "censo_inst"] == 1
    assert np.isclose(a.loc[h0, "censo_medio"], 1.5)   # 1 toda la hora + 1 media hora
    assert np.isclose(a.loc[h1, "censo_medio"], 1.0)
    assert np.isclose(b.loc[h1, "censo_medio"], 0.5)
