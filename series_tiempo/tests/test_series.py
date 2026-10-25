"""Tests del reporte de series con datos inventados dentro de cada test (sin base)."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from series_tiempo import calendario, datos
from series_tiempo.__main__ import main


def crudo_inventado(dias=800, semilla=0, inicio="2023-01-02 07:00"):
    """Series horarias con ciclo diario y semanal, como las devolvería la consulta 26."""
    rng = np.random.default_rng(semilla)
    horas = pd.date_range(inicio, periods=24 * dias, freq="h")
    perfil = 1 + 0.8 * np.sin(2 * np.pi * (horas.hour - 8) / 24)
    semana = np.where(horas.dayofweek == 0, 1.4, np.where(horas.dayofweek >= 5, 0.8, 1.0))
    lam = 3 * perfil * semana
    lleg = rng.poisson(lam)
    h = pd.DataFrame({"hora": horas, "llegadas": lleg, "llegadas_hospitalizan": rng.binomial(lleg, 0.15),
                      "llegadas_contacto_breve": rng.binomial(lleg, 0.3),
                      "ingresos_cama": rng.poisson(0.5, len(horas)), "ingresos_desde_urgencias": rng.poisson(0.4, len(horas)),
                      "altas_cama": rng.poisson(0.5, len(horas)),
                      "censo_urgencias": 20 + 5 * perfil + rng.normal(0, 2, len(horas)),
                      "censo_hospitalizacion": 60 + rng.normal(0, 3, len(horas))})
    dias_idx = pd.date_range(horas[0].normalize(), horas[-1].normalize(), freq="D")
    g = []
    for f in dias_idx:
        for dim, grupos in (("sexo", ["FEMALE", "MALE"]), ("edad", ["0-4", "18-44", "65+"]), ("destino", ["alta", "hospitalizado"])):
            for gr in grupos:
                g.append((f, dim, gr, int(rng.poisson(10))))
    grupos = pd.DataFrame(g, columns=["fecha", "dimension", "grupo", "llegadas"])
    semanas = pd.DataFrame([(w, d_, 50, 2.0 + rng.random(), 6.0, 1.8 + rng.random(), 5.0,
                             3.0 if d_ == "hospitalizado" else None)
                            for w in pd.date_range(dias_idx[0], dias_idx[-1], freq="W-MON")
                            for d_ in ("alta", "hospitalizado")],
                           columns=["semana", "destino", "episodios", "p50_h_urg", "p90_h_urg", "p50_h_urg_recortado",
                                    "p90_h_urg_recortado", "p50_dias_cama"])
    return {"horas": h, "grupos": grupos, "semanas": semanas}


def test_pascua_carnaval_y_puentes():
    assert calendario._pascua(2024) == date(2024, 3, 31)
    assert calendario._pascua(2025) == date(2025, 4, 20)
    t = calendario.tabla("2024-01-01", "2024-03-31")
    assert t.loc["2024-01-08", "festivo"] and t.loc["2024-01-08", "puente"]          # Reyes, trasladado a lunes
    assert t.loc["2024-01-06", "puente"] and t.loc["2024-01-07", "puente"]          # sábado y domingo antes
    assert t.loc["2024-01-09", "despues_de_festivo"]
    assert list(t.index[t["carnaval"]].strftime("%m-%d")) == ["02-10", "02-11", "02-12", "02-13"]
    assert t.loc["2024-03-24", "semana_santa"] and t.loc["2024-03-31", "semana_santa"]


def test_meses_y_dias_incompletos():
    c = crudo_inventado(dias=120)
    c["horas"] = c["horas"][c["horas"]["hora"] < "2023-04-10 12:00"]   # último mes casi vacío y último día cortado
    s = datos.armar(c)
    assert pd.Period("2023-04", "M") in s.meses_incompletos
    assert not s.dias.loc["2023-01-02", "completo"]          # primer día empieza a las 07h: cortado
    assert s.dias.loc["2023-02-15", "completo"]
    assert (s.horas.index.to_series().diff().dropna() == pd.Timedelta("1h")).all()


def test_tramo_continuo():
    m = pd.Series([True, True, False, True, True, True, False])
    assert datos.tramo_continuo(m).tolist() == [False, False, False, True, True, True, False]


def test_salida_dentro_del_repo_se_rechaza():
    with pytest.raises(RuntimeError):
        datos.carpeta_salida(datos.REPO_ROOT / "salida_prohibida")


def test_punta_a_punta_sin_base(tmp_path, capsys):
    salida = tmp_path / "series"
    datos.carpeta_salida(salida)
    datos.guardar_crudo(crudo_inventado(), salida)
    assert main(["--salida", str(salida), "--sin-base", "--estricto"]) == 0
    html = (salida / "reporte_series.html").read_text(encoding="utf-8")
    for sec in "ABCDEFGHIJKLMN":
        assert f">{sec}. " in html, sec
    for t in ["cobertura", "perfil_hora", "efecto_calendario", "fuerza_componentes", "pruebas_estacionariedad",
              "dispersion", "correlacion_cruzada", "grupos", "guia_decisiones"]:
        assert (salida / "tablas" / f"{t}.csv").exists(), t
    s = datos.cargar(salida)
    assert {"festivo", "carnaval", "completo"} <= set(s["dias"].columns)
    assert isinstance(s["grupos"].columns, pd.MultiIndex)

    from series_tiempo.resumen_seguro import main as resumen
    capsys.readouterr()
    assert resumen(["--salida", str(salida)]) == 0
    texto = capsys.readouterr().out
    assert "lunes" in texto                       # el día más cargado del dato inventado
    # El resumen no imprime cifras: solo franjas como "1.5 a 3" o "2-5 %", horas "08h" y ningún conteo suelto
    periodos = {"168", "365"}                     # nombres de ciclos ("semanal (168 h)"), no datos
    sueltos = [w for w in texto.replace("(", " ").replace(")", " ").split()
               if w.isdigit() and len(w) >= 3 and w not in periodos]
    assert not sueltos, sueltos
