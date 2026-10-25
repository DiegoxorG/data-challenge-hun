"""Punto de entrada sencillo: en VS Code, abre este archivo y dale a ▶ (Run Python File),
o haz doble clic en ejecutar.bat. Muestra un menú, revisa .env y VPN, corre el reporte que
elijas, lo abre en el navegador y muestra su resumen seguro (lo único que se comparte con Claude).

Sin menú (para el CI o para repetir rápido):
    python main.py --opcion series            # o cuellos, todo, series-sin-base
    python main.py --opcion series --no-abrir
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
# Para que funcione aunque no se haya hecho `pip install -e .` y desde cualquier carpeta
for p in (RAIZ, RAIZ / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OPCIONES = {
    "1": ("series", "Reporte de series de tiempo (consulta la base)"),
    "2": ("cuellos", "Reporte de cuellos de botella (consulta la base)"),
    "3": ("todo", "Los dos reportes"),
    "4": ("series-sin-base", "Rehacer el reporte de series con los datos de la última corrida (sin VPN)"),
    "0": ("salir", "Salir"),
}


def linea(txt: str = "") -> None:
    print(txt, flush=True)


def revisar_entorno(necesita_base: bool) -> bool:
    """Revisa .env, DATA_DIR y la conexión sin imprimir nunca valores (ni host ni usuario)."""
    from hun import config
    try:
        carpeta = config.data_dir()
    except RuntimeError as e:
        linea(f"✘ {e}")
        return False
    linea(f"✔ Carpeta de datos: {carpeta}")
    if not necesita_base:
        return True
    try:
        config.pg_params()
    except RuntimeError as e:
        linea(f"✘ {e}")
        return False
    linea("· Probando la conexión a la base…")
    try:
        from sqlalchemy import text

        from hun.db import engine
        with engine().connect() as con:
            con.execute(text("SELECT 1"))
    except Exception as e:  # el detalle puede traer host o usuario: solo se muestra el tipo
        linea(f"✘ No pude conectarme a la base ({type(e).__name__}).")
        linea("  ¿Está conectada la VPN (FortiClient)? ¿El usuario y la clave del .env son los tuyos?")
        return False
    linea("✔ Conexión OK")
    return True


def abrir(ruta: Path, no_abrir: bool) -> None:
    linea(f"\n📄 Reporte: {ruta}")
    if not no_abrir and ruta.exists():
        webbrowser.open(ruta.as_uri())


def correr_series(sin_base: bool, no_abrir: bool) -> int:
    from series_tiempo import datos
    from series_tiempo.__main__ import main as series
    from series_tiempo.resumen_seguro import main as resumen
    linea("\n══ Series de tiempo ══")
    r = series(["--sin-base"] if sin_base else [])
    if r != 0:
        return r
    salida = datos.carpeta_salida(None)
    abrir(salida / "reporte_series.html", no_abrir)
    linea("\n── Resumen seguro (esto sí se puede pegar en Claude) ──")
    return resumen([])


def correr_cuellos(no_abrir: bool) -> int:
    from Cuellos_botella.__main__ import main as cuellos
    from Cuellos_botella.config import validar_salida
    from Cuellos_botella.resumen_seguro import main as resumen
    linea("\n══ Cuellos de botella ══")
    r = cuellos(["--config", str(RAIZ / "Cuellos_botella" / "config.yaml"),
                 "--entrada", str(RAIZ / "sql" / "02_cuellos_botella" / "entrada.sql")])
    if r != 0:
        return r
    salida = validar_salida(None)
    abrir(salida / "reporte.html", no_abrir)
    linea("\n── Resumen seguro (esto sí se puede pegar en Claude) ──")
    return resumen(["--salida", str(salida)])


def elegir() -> str:
    linea("\n╔══════════════════════════════════════════════╗")
    linea("║   Data Challenge HUN 2026 · The Outliers      ║")
    linea("╚══════════════════════════════════════════════╝")
    for k, (_, texto) in OPCIONES.items():
        linea(f"  {k}) {texto}")
    while True:
        r = input("\nElige una opción: ").strip()
        if r in OPCIONES:
            return OPCIONES[r][0]
        linea("Opción no válida.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--opcion", choices=[v for v, _ in OPCIONES.values() if v != "salir"],
                    help="corre sin mostrar el menú")
    ap.add_argument("--no-abrir", action="store_true", help="no abrir el reporte en el navegador")
    a = ap.parse_args(argv)

    opcion = a.opcion or elegir()
    if opcion == "salir":
        return 0
    if not revisar_entorno(necesita_base=opcion != "series-sin-base"):
        return 1
    t0 = time.time()
    try:
        if opcion in ("series", "todo"):
            r = correr_series(False, a.no_abrir)
            if r != 0:
                return r
        if opcion in ("cuellos", "todo"):
            r = correr_cuellos(a.no_abrir)
            if r != 0:
                return r
        if opcion == "series-sin-base":
            r = correr_series(True, a.no_abrir)
            if r != 0:
                return r
    except FileNotFoundError as e:
        linea(f"\n✘ {e}")
        return 1
    except Exception as e:  # el traceback puede traer valores: se muestra, pero se pide compartir poco
        traceback.print_exc()
        linea(f"\n✘ Algo falló ({type(e).__name__}). Si se lo pasas a Claude, pega SOLO el tipo de error y el")
        linea("  archivo y la línea del traceback de arriba, nunca valores de datos.")
        return 1
    linea(f"\n✔ Listo en {time.time() - t0:.0f} s. El reporte y las tablas son datos del HUN: no salen de tu computador.")
    return 0


if __name__ == "__main__":
    codigo = main()
    if len(sys.argv) == 1:          # lanzado con ▶ o doble clic: que la ventana no se cierre sola
        try:
            input("\nPresiona Enter para cerrar…")
        except EOFError:
            pass
    sys.exit(codigo)
