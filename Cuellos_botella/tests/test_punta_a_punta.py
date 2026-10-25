"""Corre la herramienta completa sobre un registro aleatorio construido aquí."""
import numpy as np
import pandas as pd
import pytest

from Cuellos_botella.__main__ import analizar, main
from Cuellos_botella.config import cargar

CONFIG = """
columnas:
  persona: pid
  zona: area
  inicio: t_ini
  fin: t_fin
  etiqueta_zona: area_nombre
  atributos:
    - {columna: sexo, tipo: categorica}
    - {columna: edad, tipo: numerica}
edad_desde_anio_nacimiento: nacimiento
episodios: {umbral_min: 60, recortar_al_siguiente: true}
capacidades: {A: 5}
parametros: {tamano_min_grupo: 5, muestra_carriles: 10, minutos_bin_perfil: 30}
"""


def registro(n=400, seed=0):
    rng = np.random.default_rng(seed)
    filas = []
    for p in range(n):
        t = pd.Timestamp("2021-01-01") + pd.Timedelta(minutes=int(rng.integers(0, 60 * 24 * 100)))
        for area in ["A"] + (["B"] if rng.random() < 0.4 else []):
            dur = pd.Timedelta(minutes=float(rng.exponential(120)))
            filas.append((f"p{p}", area, f"zona {area}", t, t + dur, rng.choice(["F", "M"]), 1950 + p % 60))
            t = t + dur + pd.Timedelta(minutes=float(rng.integers(-20, 30)))
    return pd.DataFrame(filas, columns=["pid", "area", "area_nombre", "t_ini", "t_fin", "sexo", "nacimiento"])


@pytest.mark.parametrize("formato", ["csv", "parquet"])
def test_punta_a_punta(tmp_path, formato):
    df = registro()
    entrada = tmp_path / f"eventos.{formato}"
    if formato == "csv":
        df.to_csv(entrada, index=False)
    else:
        df.to_parquet(entrada, index=False)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CONFIG, encoding="utf-8")
    salida = tmp_path / "salida"
    assert main(["--config", str(cfg), "--entrada", str(entrada), "--salida", str(salida), "--estricto",
                 "--permitir-carriles"]) == 0
    html = (salida / "reporte.html").read_text(encoding="utf-8")
    for seccion in "ABCDEFGHI":
        assert f"{seccion}. " in html
    for tabla in ["calidad_resumen", "censo_horario", "transiciones_matriz", "rel_censo", "pareto_zona",
                  "comparativa_recorte", "little_zona_mes", "atributo_edad_duracion"]:
        assert (salida / "tablas" / f"{tabla}.csv").exists()


def test_carriles_sin_permiso_se_bloquean(tmp_path):
    entrada = tmp_path / "eventos.csv"
    registro(n=20).to_csv(entrada, index=False)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CONFIG, encoding="utf-8")   # trae muestra_carriles: 10
    salida = tmp_path / "salida"
    assert main(["--config", str(cfg), "--entrada", str(entrada), "--salida", str(salida)]) == 2
    assert not (salida / "reporte.html").exists()


def test_salida_dentro_del_repo_se_rechaza():
    from Cuellos_botella.config import REPO_ROOT, validar_salida
    with pytest.raises(RuntimeError):
        validar_salida(REPO_ROOT / "salidas_prohibidas")


def test_ninguna_figura_vacia(tmp_path):
    entrada = tmp_path / "eventos.parquet"
    registro().to_parquet(entrada, index=False)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(CONFIG, encoding="utf-8")
    reg = analizar(cargar(cfg), str(entrada), tmp_path / "salida", estricto=True)
    vacias = []
    for f in reg.figuras:
        datos = [t for t in f.fig.data if any(len(v) for k in ("x", "y", "z", "q1", "value")
                                               if (v := getattr(t, k, None)) is not None and hasattr(v, "__len__"))
                 or getattr(t, "type", "") == "sankey"]
        if not datos:
            vacias.append(f.titulo)
    assert not vacias, vacias
