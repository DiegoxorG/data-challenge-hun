import pandas as pd

from Cuellos_botella.calidad import cobertura_mensual, detectar_solapes


def t(h):
    return pd.Timestamp("2020-01-01") + pd.Timedelta(hours=h)


def test_solapes_misma_zona_y_entre_zonas():
    df = pd.DataFrame([
        ("A", "z1", t(0), t(10)),
        ("A", "z1", t(5), t(8)),    # dentro de z1 abierto: solape en la misma zona
        ("A", "z2", t(9), t(12)),   # z1 sigue abierto hasta las 10: solape con otra zona
        ("A", "z2", t(12), t(13)),  # empieza justo cuando termina el z2 previo: NO es solape
        ("B", "z1", t(1), t(3)),    # otra persona: nunca se compara con A
    ], columns=["persona", "zona", "inicio", "fin"])
    flags, pares = detectar_solapes(df)
    assert list(flags["solape_misma_zona"]) == [False, True, False, False, False]
    assert list(flags["solape_otra_zona"]) == [False, False, True, False, False]
    p = pares.set_index(["zona_previa", "zona_posterior"])
    assert p.loc[("z1", "z1"), "n"] == 1 and p.loc[("z1", "z2"), "n"] == 1
    assert p.loc[("z1", "z2"), "p50_min"] == 60     # se solapan de 9 a 10
    assert ("z2", "z2") not in p.index


def test_cobertura_marca_meses_incompletos():
    filas = []
    for mes, n in (("2020-01", 100), ("2020-02", 100), ("2020-03", 100), ("2020-04", 10)):
        dias = pd.date_range(f"{mes}-01", periods=28, freq="D")
        for i in range(n):
            filas.append((f"p{i}", "z", dias[i % 28], dias[i % 28] + pd.Timedelta(hours=1)))
    df = pd.DataFrame(filas, columns=["persona", "zona", "inicio", "fin"])
    cob = cobertura_mensual(df, frac=0.5, cobertura_min=0.9).set_index("mes")
    assert cob.loc["2020-04", "incompleto"]
    assert not cob.loc["2020-02", "incompleto"]
