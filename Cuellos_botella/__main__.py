"""Uso:
    python -m Cuellos_botella --config Cuellos_botella/config.yaml --entrada <archivo.csv|parquet> [--salida <carpeta>]

Sin --salida escribe en DATA_DIR/cuellos_botella_salidas. Nunca escribe dentro del repo.
En consola solo imprime avance y avisos genéricos, sin cifras de los datos.
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

from . import (atributos, calidad, carga, censo, cola, episodios, flujos, relaciones, reporte, tiempo,
               transiciones)
from .comun import Contexto, Registro
from .config import Config, cargar, validar_salida

# La consola de Windows (cp1252) no imprime algunos caracteres; forzamos UTF-8 como en check_no_data.py
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


PASOS = [("episodios y trayectorias", episodios.correr), ("censo", censo.correr),
         ("duración y flujo por zona", flujos.correr), ("transiciones", transiciones.correr),
         ("relaciones", relaciones.correr), ("tiempo", tiempo.correr),
         ("atributos", atributos.correr), ("cola larga", cola.correr)]
OBLIGATORIOS = ("episodios y trayectorias", "censo")   # el resto depende de estos


def analizar(cfg: Config, entrada: str, salida: Path, estricto: bool = False) -> Registro | None:
    """Corre todas las secciones y devuelve el registro de figuras/tablas (None si no hay filas válidas)."""
    reg = Registro(salida)
    print("· leyendo entrada")
    df, tipos = carga.normalizar(carga.leer(entrada, cfg), cfg)
    etq = carga.etiquetas_zona(df)

    print("· calidad de datos")
    validos, meses = calidad.analizar(df, tipos, cfg, reg, etq)
    del df
    if validos.empty:
        return None
    zonas = list(validos["zona"].value_counts().index)
    ctx = Contexto(cfg=cfg, seg=validos, etiquetas=etq, zonas=zonas, meses_incompletos=meses)

    log = salida / "errores.log"
    log.unlink(missing_ok=True)
    for nombre, fn in PASOS:
        print(f"· {nombre}")
        try:
            fn(ctx, reg)
        except Exception as e:
            if estricto or nombre in OBLIGATORIOS:
                raise
            reg.errores.append(nombre)
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"== {nombre} ==\n{traceback.format_exc()}\n")
            print(f"  ! no se pudo generar '{nombre}' ({type(e).__name__}); detalle en errores.log")
    return reg


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m Cuellos_botella", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--entrada", required=True)
    ap.add_argument("--salida", default=None)
    ap.add_argument("--estricto", action="store_true", help="detenerse ante el primer error de una sección")
    a = ap.parse_args(argv)

    t_ini = time.time()
    cfg = cargar(a.config)
    salida = validar_salida(a.salida)
    print(f"Salida: {salida}")
    reg = analizar(cfg, a.entrada, salida, a.estricto)
    if reg is None:
        print("No quedaron filas válidas; revisa el mapeo de columnas en el config.")
        return 1

    out = reporte.escribir(reg, cfg, a.entrada)
    print(f"\nListo en {time.time() - t_ini:.0f} s: {len(reg.figuras)} figuras, {len(reg.tablas)} tablas.")
    for av in reg.avisos:
        print(f"  aviso: {av}")
    print(f"Reporte: {out}")
    print("Para compartir con Claude usa SOLO: python -m Cuellos_botella.resumen_seguro --salida <carpeta>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
