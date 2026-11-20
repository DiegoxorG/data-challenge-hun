"""Test del resumen seguro de perfiles con tablas inventadas con la forma de las de Cuellos_botella."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import resumen_seguro_perfiles as R  # noqa: E402


def _tablas(tmp: Path) -> Path:
    t = tmp / "tablas"
    t.mkdir(parents=True)
    pd.DataFrame({"zona": ["U", "H"], "nombre": ["Urgencias", "Hospitalización"], "n": [1000, 200],
                  "p50": [120.0, 2880.0], "p90": [600.0, 10000.0]}).to_csv(t / "duracion_percentiles.csv", index=False)
    pd.DataFrame({"atributo": "edad", "zona": ["U"] * 3, "grupo": ["[0.0, 5.0)", "[18.0, 30.0)", "[75.0, 130.0)"],
                  "n": [100, 600, 300], "media": 0, "p50": [60.0, 100.0, 400.0], "p90": [200.0, 500.0, 2000.0]}
                 ).to_csv(t / "atributo_edad_duracion.csv", index=False)
    pd.DataFrame({"atributo": "edad", "zona": ["U"] * 6,
                  "grupo": ["[0.0, 5.0)"] * 2 + ["[18.0, 30.0)"] * 2 + ["[75.0, 130.0)"] * 2,
                  "destino": ["H", R.FIN] * 3, "n": [2, 98, 30, 570, 120, 180]}).to_csv(t / "atributo_edad_destino.csv", index=False)
    pd.DataFrame({"atributo": "gender_concept_id", "zona": ["U", "U"], "grupo": ["8507", "8532"], "n": [480, 520],
                  "media": 0, "p50": [118.0, 122.0], "p90": [580.0, 610.0]}).to_csv(t / "atributo_gender_concept_id_duracion.csv", index=False)
    return tmp


def test_resumen_perfiles_en_palabras(tmp_path, capsys):
    assert R.resumir(_tablas(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "75+ años" in out and "0-4 años" in out and "mujeres" in out
    assert "pasan a Hospitalización" in out
    linea_mayores = next(l for l in out.splitlines() if "75+ años" in l)
    assert "más que" in linea_mayores                         # los mayores se quedan y se hospitalizan más
    assert not [w for w in out.replace("(", " ").split() if w.isdigit() and len(w) >= 3]


def test_sin_tablas_avisa(tmp_path, capsys):
    assert R.resumir(tmp_path) == 1
