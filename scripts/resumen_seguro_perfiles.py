"""Resumen seguro de PERFILES DE PACIENTES (sexo y edad): solo palabras, franjas y comparaciones.

Lee las tablas agregadas que ya deja Cuellos_botella (sección H · Atributos):
  tablas/atributo_<atributo>_duracion.csv   duración por zona y grupo (n, media, percentiles)
  tablas/atributo_<atributo>_destino.csv    destino al salir de cada zona por grupo (proporción)
  tablas/duracion_percentiles.csv           duración global por zona (para comparar)

y dice, para cada zona y cada grupo de sexo y de edad:
  - qué tan grande es el grupo ("pocos", "bastantes"...)
  - su duración típica (franja) y frente a la de toda la zona ("parecido a", "bastante más que...")
  - qué proporción pasa a otra zona (p. ej. de urgencias a hospitalización) frente al total

Uso:  python scripts/resumen_seguro_perfiles.py [--salida <carpeta de Cuellos_botella>]
      (por defecto DATA_DIR/cuellos_botella_salidas). No se conecta a la base.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from hun.palabras import cuanto, franja, veces

FIN = "(fin del episodio)"
SEXO = {"8507": "hombres", "8532": "mujeres", "8507.0": "hombres", "8532.0": "mujeres"}
NOMBRE_ATRIBUTO = {"gender_concept_id": "sexo", "edad": "edad"}


def etiqueta(attr: str, g: str) -> str:
    if attr == "gender_concept_id":
        return SEXO.get(str(g), str(g))
    if attr == "edad" and g.startswith("["):          # "[18.0, 30.0)" -> "18-29 años"
        try:
            a, b = (float(v) for v in g.strip("[)").split(","))
            return f"{int(a)}+ años" if b >= 120 else f"{int(a)}-{int(b) - 1} años"
        except ValueError:
            return g
    return g


def resumir(carpeta: Path) -> int:
    t = carpeta / "tablas"
    dur_glob = t / "duracion_percentiles.csv"
    if not dur_glob.exists():
        print(f"No encontré las tablas de Cuellos_botella en {t}. Corre primero la herramienta "
              "(python -m Cuellos_botella --config ... --entrada ...).")
        return 1
    g = pd.read_csv(dur_glob, dtype={"zona": str})
    nombre = dict(zip(g["zona"], g["nombre"])) if "nombre" in g else {}
    p50_zona = dict(zip(g["zona"], g["p50"]))
    p90_zona = dict(zip(g["zona"], g["p90"])) if "p90" in g else {}
    n = lambda z: nombre.get(z, z)  # noqa: E731

    archivos = sorted(t.glob("atributo_*_duracion.csv"))
    if not archivos:
        print("Cuellos_botella no generó la sección H (atributos). Revisa 'atributos' en Cuellos_botella/config.yaml.")
        return 1
    print("RESUMEN SEGURO DE PERFILES DE PACIENTES (solo palabras y franjas)")
    for p in archivos:
        d = pd.read_csv(p, dtype={"zona": str, "grupo": str})
        if d.empty:
            continue
        attr = d["atributo"].iloc[0]
        print(f"\n== Por {NOMBRE_ATRIBUTO.get(attr, attr)} ==")
        pd_dest = p.with_name(p.name.replace("_duracion", "_destino"))
        dest = pd.read_csv(pd_dest, dtype={"zona": str, "grupo": str, "destino": str}) if pd_dest.exists() else None
        for z, dz in d.groupby("zona", sort=False):
            tot = dz["n"].sum()
            print(f"- {n(z)}: mediana de toda la zona {franja(p50_zona.get(z))}")
            # Proporción que pasa a otra zona (no termina aquí), global y por grupo
            pasa_glob, pasa = None, {}
            if dest is not None:
                dd = dest[dest["zona"] == z]
                otras = dd[dd["destino"] != FIN]
                if len(otras):
                    principal = otras.groupby("destino")["n"].sum().idxmax()
                    pasa_glob = dd.loc[dd["destino"] == principal, "n"].sum() / dd["n"].sum()
                    por = dd.groupby("grupo")["n"].sum()
                    pasa = (dd[dd["destino"] == principal].groupby("grupo")["n"].sum() / por).to_dict()
                    print(f"    de esta zona pasan a {n(principal)}: {cuanto(pasa_glob)} en total")
            for _, r in dz.iterrows():
                if r["grupo"] in ("otros", "sin dato"):
                    continue
                linea = (f"    {etiqueta(attr, r['grupo'])}: {cuanto(r['n'] / tot)} de las estancias; "
                         f"mediana {franja(r['p50'])} ({veces(r['p50'], p50_zona.get(z))} la de la zona)")
                if "p90" in r and p90_zona.get(z):
                    linea += f"; p90 {veces(r['p90'], p90_zona.get(z))} el de la zona"
                if pasa_glob:
                    linea += f"; pasan a {n(principal)} {veces(pasa.get(r['grupo'], float('nan')), pasa_glob)} el promedio"
                print((linea + ".").replace(" a el ", " al ").replace(" de el ", " del "))
    print("\nTodo lo de arriba se puede compartir: palabras, franjas y comparaciones cualitativas.")
    return 0


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=None, help="carpeta de salida de Cuellos_botella")
    a = ap.parse_args(argv)
    if a.salida:
        carpeta = Path(a.salida)
    else:
        from hun.config import data_dir
        carpeta = data_dir() / "cuellos_botella_salidas"
    return resumir(carpeta)


if __name__ == "__main__":
    sys.exit(main())
