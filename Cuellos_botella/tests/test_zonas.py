"""Filtros y agrupación de zonas, códigos numéricos y exclusión de estancias largas."""
import pandas as pd
import pytest

from Cuellos_botella import carga, episodios
from Cuellos_botella.comun import Contexto, Registro
from Cuellos_botella.config import cargar

BASE = """
columnas: {persona: pid, zona: cid, inicio: ini, fin: fin}
episodios: {umbral_min: 60, recortar_al_siguiente: true}
zonas_incluir: ["9203", "3045729", "9201"]
zonas_agrupar:
  urgencias: {codigos: ["9203", "3045729"], etiqueta: "Urgencias"}
  hospitalizacion: {codigos: ["9201"], etiqueta: "Hospitalización"}
"""


def cfg_de(tmp_path, extra=""):
    p = tmp_path / "config.yaml"
    p.write_text(BASE + extra, encoding="utf-8")
    return cargar(p)


def t(h):
    return pd.Timestamp("2024-03-01") + pd.Timedelta(hours=h)


def crudo(filas):
    return pd.DataFrame(filas, columns=["pid", "cid", "ini", "fin"])


def test_codigos_float_sin_punto_cero(tmp_path):
    # Un concept_id con nulos llega como float: 9203.0 debe coincidir con "9203" del config
    df = crudo([(1, 9203.0, t(0), t(0)), (1, None, t(1), t(2))])
    out, _ = carga.normalizar(df, cfg_de(tmp_path))
    assert list(out["zona_original"]) == ["9203"]


def test_incluir_y_agrupar(tmp_path):
    df = crudo([(1, 9203, t(0), t(0)), (1, 3045729, t(0), t(3)), (1, 9201, t(3), t(50)),
                (1, 581479, t(1), t(1)), (2, 0, t(5), t(6))])
    out, _ = carga.normalizar(df, cfg_de(tmp_path))
    assert set(out["zona"]) == {"urgencias", "hospitalizacion"}      # 581479 y 0 fuera
    assert set(out.loc[out["zona"] == "urgencias", "etiqueta"]) == {"Urgencias"}
    assert sorted(out["zona_original"]) == ["3045729", "9201", "9203"]


def test_codigo_en_dos_grupos_es_error(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text('columnas: {persona: a, zona: b, inicio: c, fin: d}\n'
                 'zonas_agrupar:\n  a: {codigos: ["1"]}\n  b: {codigos: ["1"]}\n', encoding="utf-8")
    with pytest.raises(ValueError):
        cargar(p)


def test_llegada_y_atencion_son_una_estancia(tmp_path):
    # Marca de llegada (0 min) solapada con la atención: una sola estancia de urgencias de 3 h
    df = crudo([(1, 9203, t(0), t(0)), (1, 3045729, t(0), t(3)), (1, 9201, t(4), t(30))])
    seg, _ = carga.normalizar(df, cfg_de(tmp_path))
    seg["episodio"] = episodios.asignar_episodios(seg, 60)
    est = episodios.construir_estancias(seg)
    assert list(est["zona"]) == ["urgencias", "hospitalizacion"]
    assert est.loc[0, "min_original"] == 180


def test_excluir_estancias_largas_no_toca_episodios(tmp_path):
    cfg = cfg_de(tmp_path, "excluir_estancias_largas: {urgencias: 7}\n")
    df = crudo([(1, 3045729, t(0), t(24 * 8)),            # 8 días en urgencias: se excluye
                (2, 3045729, t(0), t(2)), (2, 9201, t(2), t(24 * 3))])
    seg, _ = carga.normalizar(df, cfg)
    ctx = Contexto(cfg=cfg, seg=seg, etiquetas=carga.etiquetas_zona(seg), zonas=["urgencias", "hospitalizacion"])
    reg = Registro(tmp_path / "salida")
    episodios.correr(ctx, reg)
    assert len(ctx.epi) == 2                                # los episodios no cambian
    assert len(ctx.est) == 2 and set(ctx.est["persona"]) == {"2"}
    tabla = pd.read_csv(tmp_path / "salida" / "tablas" / "estancias_excluidas.csv")
    assert tabla.loc[0, "excluidas"] == 1
