import numpy as np
import pandas as pd

from Cuellos_botella.cola import curva_pareto
from Cuellos_botella.comun import FIN
from Cuellos_botella.transiciones import matriz


def test_matriz_conteos_y_probabilidades():
    est = pd.DataFrame({"zona": ["a", "a", "a", "b", "b", "c"],
                        "destino": ["b", "b", FIN, "c", FIN, FIN]})
    m = matriz(est).set_index(["origen", "destino"])
    assert m.loc[("a", "b"), "n"] == 2 and np.isclose(m.loc[("a", "b"), "probabilidad"], 2 / 3)
    assert np.isclose(m.loc[("a", FIN), "probabilidad"], 1 / 3)
    assert np.isclose(m.loc[("b", "c"), "probabilidad"], 0.5)
    assert np.allclose(m.groupby(level="origen")["probabilidad"].sum(), 1)


def test_curva_pareto():
    x, y = curva_pareto(np.array([90.0, 5.0, 5.0, 0.0]))
    assert np.isclose(np.interp(0.25, x, y), 0.9)    # la estancia más larga (25 %) aporta el 90 %
    assert np.isclose(y[-1], 1.0) and y[0] == 0
