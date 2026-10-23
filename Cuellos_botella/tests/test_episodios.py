import numpy as np
import pandas as pd

from Cuellos_botella.episodios import asignar_episodios, construir_estancias


def seg(filas):
    df = pd.DataFrame(filas, columns=["persona", "zona", "inicio", "fin"])
    df["inicio"] = pd.to_datetime(df["inicio"])
    df["fin"] = pd.to_datetime(df["fin"])
    return df


def test_union_por_umbral():
    df = seg([
        ("A", "z1", "2020-01-01 08:00", "2020-01-01 09:00"),
        ("A", "z2", "2020-01-01 10:00", "2020-01-01 10:30"),  # hueco de 60 min exactos: sigue
        ("A", "z1", "2020-01-01 11:31", "2020-01-01 12:00"),  # hueco de 61 min: episodio nuevo
        ("B", "z1", "2020-01-01 08:00", "2020-01-01 12:00"),
        ("B", "z2", "2020-01-01 09:00", "2020-01-01 09:10"),  # solapado: mismo episodio
        ("B", "z1", "2020-01-01 12:30", "2020-01-01 13:00"),  # 30 min después del máximo fin previo
    ])
    ep = asignar_episodios(df, umbral_min=60)
    assert ep[0] == ep[1] != ep[2]
    assert ep[3] == ep[4] == ep[5]
    assert ep.nunique() == 3
    # Con umbral 0 el segmento solapado sigue unido (se compara con el máximo fin acumulado)
    assert asignar_episodios(df, umbral_min=0).nunique() == 5


def test_union_por_caso():
    df = seg([("A", "z1", "2020-01-01 08:00", "2020-01-01 09:00"),
              ("A", "z1", "2020-01-05 08:00", "2020-01-05 09:00")])
    df["caso"] = ["c1", "c1"]
    assert asignar_episodios(df, 60, usar_caso=True).nunique() == 1
    assert asignar_episodios(df, 60, usar_caso=False).nunique() == 2


def test_estancias_secuencia_y_recorte():
    df = seg([
        ("A", "z1", "2020-01-01 08:00", "2020-01-01 08:30"),
        ("A", "z1", "2020-01-01 08:30", "2020-01-01 10:00"),  # misma zona seguida: una sola estancia
        ("A", "z2", "2020-01-01 09:00", "2020-01-01 15:00"),  # empieza con z1 abierta
        ("A", "z3", "2020-01-01 15:20", "2020-01-01 16:00"),
    ])
    df["episodio"] = asignar_episodios(df, 60)
    est = construir_estancias(df)
    assert list(est["zona"]) == ["z1", "z2", "z3"]
    assert list(est["n_segmentos"]) == [2, 1, 1]
    assert list(est["destino"]) == ["z2", "z3", "(fin del episodio)"]
    z1 = est.iloc[0]
    assert z1["recortada"] and z1["fin_recortado"] == pd.Timestamp("2020-01-01 09:00")
    assert np.isclose(z1["min_original"], 120) and np.isclose(z1["min_recortado"], 60)
    assert np.isclose(z1["hueco_min"], -60)           # solape de 1 h
    assert np.isclose(est.iloc[1]["hueco_min"], 20)   # hueco de 20 min sin registro
    assert not est.iloc[1]["recortada"]
