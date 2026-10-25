"""Uso:
    python -m series_tiempo [--salida <carpeta>] [--sin-base] [--estricto]

Corre las consultas AGREGADAS sql/01_episodios/26-28 contra la base (VPN + .env), arma las series
por hora, día y semana con el calendario colombiano, y escribe en DATA_DIR/series_tiempo:
  reporte_series.html   el reporte para decidir el modelo (abre sin internet)
  datos/*.parquet       las series listas para modelar (series_tiempo.cargar())
  tablas/*.csv          las métricas de cada sección
Con --sin-base reusa los datos de una corrida anterior (no se conecta).
En consola solo imprime avance, sin cifras de los datos.
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback

from . import datos, secciones
from .reporte import Registro, escribir

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

INTRO = """
<h3>Para qué es esto</h3>
<p>Reúne todo lo que hace falta mirar antes de elegir un modelo de series de tiempo para urgencias:
cobertura, tendencia, los ciclos del día, la semana y el año, el efecto de festivos y temporadas, la
descomposición, la autocorrelación, la estacionariedad, cómo se distribuyen los conteos y cómo se
relacionan las llegadas con los ingresos, las altas y el censo.</p>
<p>Cada gráfica tiene tres partes: <b>qué muestra</b>, <b>cómo leerla</b> y <b>qué implica para el modelo</b>.
La sección N junta las decisiones de modelado y dónde mirar cada una.</p>
<h3>Qué se cuenta</h3>
<p><b>Llegadas</b> = episodios que empiezan en urgencias (definición de <code>sql/01_episodios/_episodios.sql</code>),
por hora de llegada. <b>Ingresos</b> y <b>altas de cama</b> = inicio y fin de cada hospitalización. <b>Censos</b> =
personas presentes, como la consulta 25. Solo entran días completos: los meses incompletos y los días cortados
por el extracto quedan fuera de todos los cálculos.</p>
<h3>Para modelar</h3>
<p>Las series están en <code>datos/series_horarias.parquet</code> y <code>datos/series_diarias.parquet</code> (con
festivos, puentes, Semana Santa, Carnaval y la columna <code>completo</code>). Desde Python:
<code>from series_tiempo import cargar; s = cargar()</code>. El notebook
<code>notebooks/01_series_tiempo_arranque.ipynb</code> trae una primera validación con modelos de referencia.</p>
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m series_tiempo", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", default=None, help="carpeta de salida (por defecto DATA_DIR/series_tiempo)")
    ap.add_argument("--sin-base", action="store_true", help="reusa los datos guardados de una corrida anterior")
    ap.add_argument("--estricto", action="store_true", help="detenerse ante el primer error de una sección")
    a = ap.parse_args(argv)

    t0 = time.time()
    salida = datos.carpeta_salida(a.salida)
    print(f"Salida: {salida}")
    if a.sin_base:
        print("· leyendo la corrida anterior")
        crudo = datos.leer_guardado(salida)
    else:
        print("· consultando la base (26, 27 y 28; puede tardar unos minutos)")
        crudo = datos.leer_base()
        datos.guardar_crudo(crudo, salida)
    s = datos.armar(crudo)
    if not s.dias["completo"].any():
        print("No hay ningún día completo: revisa el rango de la base.")
        return 1
    datos.guardar_series(s, salida)

    reg = Registro(salida)
    log = salida / "errores.log"
    log.unlink(missing_ok=True)
    for nombre, fn in secciones.SECCIONES:
        print(f"· {nombre}")
        try:
            fn(s, reg)
        except Exception as e:
            if a.estricto:
                raise
            reg.errores.append(nombre)
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"== {nombre} ==\n{traceback.format_exc()}\n")
            print(f"  ! no se pudo generar '{nombre}' ({type(e).__name__}); detalle en errores.log")
    if s.meses_incompletos:
        reg.avisos.insert(0, "Hay meses incompletos; se sombrean en las series y no entran en los cálculos.")
    out = escribir(reg, INTRO, "consultas 26-28" + (" (corrida guardada)" if a.sin_base else ""))
    n_fig = sum(1 for p in reg.piezas if type(p).__name__ == "Fig")
    print(f"\nListo en {time.time() - t0:.0f} s: {n_fig} figuras.")
    print(f"Reporte: {out}")
    print("Para compartir con Claude usa SOLO: python -m series_tiempo.resumen_seguro")
    return 0


if __name__ == "__main__":
    sys.exit(main())
