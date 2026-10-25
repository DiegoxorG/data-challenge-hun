"""Resumen seguro de las salidas de la herramienta de cuellos de botella.

Lee las tablas CSV generadas y las imprime SOLO en palabras, franjas y comparaciones
cualitativas ("la mayoría", "1-4 h", "entre 1.5 y 3 veces", "10h-13h"). Sin conteos,
sin fechas y sin valores individuales. Es lo único que se puede compartir con Claude.

Uso:  python -m Cuellos_botella.resumen_seguro [--salida <carpeta de salidas>]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

FIN = "(fin del episodio)"
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]


# --- traducción a palabras -------------------------------------------------------
def cuanto(p: float) -> str:
    if pd.isna(p) or p == 0:
        return "ninguno"
    if p < 0.01:
        return "casi ninguno"
    if p < 0.10:
        return "pocos"
    if p < 0.50:
        return "bastantes"
    if p < 0.90:
        return "la mayoría"
    return "casi todos"


def franja(minutos: float) -> str:
    if pd.isna(minutos):
        return "sin dato"
    if minutos < 0:
        return "solape de " + franja(-minutos)
    if minutos == 0:
        return "0 (contiguo)"
    for limite, etiqueta in [(1, "menos de 1 min"), (15, "1-15 min"), (60, "15 min-1 h"), (240, "1-4 h"),
                             (720, "4-12 h"), (1440, "12-24 h"), (4320, "1-3 días"), (10080, "3-7 días"),
                             (43200, "1-4 semanas")]:
        if minutos < limite:
            return etiqueta
    return "más de un mes"


def veces(a: float, b: float) -> str:
    if pd.isna(a) or pd.isna(b) or b <= 0:
        return "no comparable con"
    r = a / b
    for limite, txt in [(0.5, "menos de la mitad de"), (0.8, "menos que"), (1.25, "parecido a"),
                        (1.5, "algo más que (1.25 a 1.5 veces)"), (3, "bastante más que (1.5 a 3 veces)"),
                        (10, "mucho más que (3 a 10 veces)")]:
        if r < limite:
            return txt
    return "muchísimo más que (más de 10 veces)"


def es(a: float, b: float) -> str:
    """'es parecido a', 'es bastante más que (...)' o 'no es comparable con'."""
    v = veces(a, b)
    return "no es comparable con" if v == "no comparable con" else "es " + v


def rango_horas(bins: list[int], min_bin: int) -> str:
    """Bins consecutivos del día -> '10h-13h'."""
    a = bins[0] * min_bin
    b = (bins[-1] + 1) * min_bin
    fmt = lambda m: f"{(m // 60) % 24:02d}h" + (f"{m % 60:02d}" if m % 60 else "")  # noqa: E731
    return f"{fmt(a)}-{fmt(b)}"


def tramos(mask: np.ndarray, min_bin: int) -> list[str]:
    """Franjas del día donde mask es True, como lista de rangos."""
    out, ini = [], None
    for i, v in enumerate(list(mask) + [False]):
        if v and ini is None:
            ini = i
        if not v and ini is not None:
            out.append(rango_horas(list(range(ini, i)), min_bin))
            ini = None
    return out


def ventana_pico(v: np.ndarray, ancho: int, maximo: bool = True) -> list[int]:
    """Índices de la ventana circular de `ancho` bins con mayor (o menor) suma."""
    n = len(v)
    sumas = np.array([v[[(i + k) % n for k in range(ancho)]].sum() for i in range(n)])
    i = int(np.argmax(sumas) if maximo else np.argmin(sumas))
    return [i + k for k in range(ancho)]   # puede pasar de n: rango_horas usa módulo 24 h


# --- lectura ----------------------------------------------------------------------
class Tablas:
    def __init__(self, carpeta: Path):
        self.carpeta = carpeta / "tablas"

    def __call__(self, nombre: str) -> pd.DataFrame | None:
        p = self.carpeta / f"{nombre}.csv"
        if not p.exists():
            return None
        return pd.read_csv(p, dtype={"zona": str, "destino": str, "origen": str, "zona_previa": str,
                                     "zona_posterior": str, "siguiente": str, "zona_final": str,
                                     "zona_inicial_siguiente": str})


def nombres(t: Tablas) -> dict[str, str]:
    d = t("duracion_percentiles")
    return {} if d is None else dict(zip(d["zona"], d["nombre"]))


def titulo(txt: str) -> None:
    print(f"\n== {txt} ==")


def resumir(t: Tablas) -> None:
    nom = nombres(t)
    n = lambda z: FIN if z == FIN else nom.get(z, "zona sin nombre")  # noqa: E731

    titulo("A · Calidad de datos")
    r = t("calidad_resumen")
    if r is not None:
        r = r.set_index("indicador")
        for ind, txt in [("clave_nula", "filas con persona/zona/fechas nulas o ilegibles"),
                         ("fin_antes_de_inicio", "filas con fin antes del inicio"),
                         ("duracion_cero", "filas con duración cero"),
                         ("duplicadas", "filas duplicadas"),
                         ("solape_misma_zona", "segmentos que solapan con otro de la misma zona y persona"),
                         ("solape_otra_zona", "segmentos que empiezan con otra zona aún abierta")]:
            if ind in r.index:
                print(f"  {txt}: {cuanto(r.loc[ind, 'proporcion'])}")
    nt = t("calidad_nulos_tipos")
    if nt is not None:
        con = nt[(nt["p_nulos"] > 0) | (nt["no_interpretables"] > 0)]
        if con.empty:
            print("  columnas con nulos: ninguna")
        for _, f in con.iterrows():
            print(f"  nulos en {f['columna']}: {cuanto(f['p_nulos'])}"
                  + (" (además hay fechas ilegibles)" if f["no_interpretables"] > 0 else ""))
    cob = t("cobertura_mensual")
    if cob is not None and len(cob):
        inc = cob["incompleto"].astype(bool).to_numpy()
        if not inc.any():
            print("  meses incompletos: ninguno")
        else:
            donde = []
            if inc[0]:
                donde.append("al inicio")
            if inc[-1]:
                donde.append("al final")
            if inc[1:-1].any():
                donde.append("en medio del periodo")
            cuantos = "uno" if inc.sum() == 1 else "varios"
            print(f"  meses incompletos: {cuantos}, {' y '.join(donde)} (se excluyen de perfiles, censo y Little)")
    sp = t("solapes_pares")
    if sp is not None and len(sp):
        sp = sp.sort_values("proporcion_de_posterior", ascending=False).head(5)
        print("  solapes más comunes (zona que empieza / zona aún abierta):")
        for _, f in sp.iterrows():
            print(f"    {n(f['zona_posterior'])} con {n(f['zona_previa'])} abierta: "
                  f"{cuanto(f['proporcion_de_posterior'])}; solape típico {franja(f['p50_min'])}")
    ex = t("duraciones_extremas")
    if ex is not None:
        for _, f in ex.iterrows():
            print(f"  {n(f['zona'])}: segmentos > 24 h {cuanto(f['p_mas_24h'])}, > 7 días {cuanto(f['p_mas_7d'])}, "
                  f"> 30 días {cuanto(f['p_mas_30d'])}")

    titulo("B · Episodios y trayectorias")
    er = t("episodios_resumen")
    if er is not None:
        er = er.set_index("indicador")["valor"]
        print(f"  episodios de una sola zona: {cuanto(er.get('p_episodios_una_estancia'))}")
        if "p_episodios_irregulares" in er:
            print(f"  episodios irregulares (una zona se repite o el flujo retrocede, p. ej. hospitalización → "
                  f"urgencias): {cuanto(er.get('p_episodios_irregulares'))}")
        print(f"  estancias que siguen abiertas cuando empieza la siguiente: {cuanto(er.get('p_estancias_recortables'))}")
        print(f"  recorte aplicado en el reporte: {'sí' if er.get('recorte_aplicado') == 1 else 'no'}")
    st = t("secuencias_top")
    if st is not None:
        print("  secuencias más frecuentes:")
        for _, f in st.head(6).iterrows():
            print(f"    {f['secuencia']}: {cuanto(f['proporcion'])}")
    ee = t("estancias_excluidas")
    if ee is not None:
        for _, f in ee.iterrows():
            print(f"  {n(f['zona'])}: estancias de más de {f['limite_dias']:g} días excluidas del reporte: "
                  f"{cuanto(f['p_excluidas'])}")
    cr = t("comparativa_recorte")
    if cr is not None:
        print("  efecto del recorte (con recorte frente a sin recorte):")
        for _, f in cr.iterrows():
            print(f"    {n(f['zona'])}: afecta a {cuanto(f['p_recortadas'])}; mediana "
                  f"{veces(f['p50_min_recortado'], f['p50_min_original'])} la versión original; censo medio "
                  f"{veces(f['censo_medio_recortado'], f['censo_medio_original'])} la versión original")

    titulo("C · Duración y flujo por zona")
    dp = t("duracion_percentiles")
    if dp is not None:
        for _, f in dp.iterrows():
            print(f"  {n(f['zona'])}: mediana {franja(f['p50'])}, p90 {franja(f['p90'])}; "
                  f"el p90 {es(f['p90'], f['p50'])} la mediana")
    fl = t("flujo_hora_dia")
    if fl is not None and len(fl):
        min_bin = 1440 // (fl["bin"].max() + 1)
        ancho = max(1, 180 // min_bin)
        for z, fz in fl.groupby("zona", sort=False):
            ent = fz.groupby("bin")["entradas_prom"].mean().to_numpy()
            if np.nansum(ent) == 0:
                continue
            sal = fz.groupby("bin")["salidas_prom"].mean().to_numpy()
            pico, valle = ventana_pico(ent, ancho), ventana_pico(ent, ancho, maximo=False)
            dias = fz.groupby("dow")["entradas_prom"].sum()
            print(f"  {n(z)}: entradas pico {rango_horas(pico, min_bin)}, más tranquilas "
                  f"{rango_horas(valle, min_bin)}; la hora pico {es(np.nanmax(ent), np.nanmin(ent[ent > 0]) if (ent > 0).any() else np.nan)} "
                  f"la más tranquila")
            print(f"    día con más entradas: {DIAS[int(dias.idxmax())]}; con menos: {DIAS[int(dias.idxmin())]} "
                  f"({veces(dias.max(), dias.min())})")
            llena = tramos(ent - sal > 0.05 * np.nanmax(ent), min_bin)
            print(f"    franjas donde entran más de las que salen: {', '.join(llena) if llena else 'ninguna clara'}")

    titulo("D · Censo")
    cd = t("censo_distribucion")
    if cd is not None:
        for _, f in cd.iterrows():
            linea = f"  {n(f['zona'])}: el p90 del censo horario {es(f['p90'], f['p50'])} la mediana"
            if not pd.isna(f.get("capacidad", np.nan)):
                linea += (f"; la mediana {es(f['p50'], f['capacidad'])} la capacidad de referencia; horas sobre "
                          f"la capacidad: {cuanto(f['p_horas_sobre_capacidad'])}")
            print(linea)
    ch = t("censo_hora_dia")
    if ch is not None:
        for z, cz in ch.groupby("zona", sort=False):
            h = cz.groupby("h")["media"].mean().reindex(range(24)).fillna(0).to_numpy()
            if h.sum() == 0:
                continue
            print(f"  {n(z)}: censo más alto {rango_horas(ventana_pico(h, 3), 60)}, más bajo "
                  f"{rango_horas(ventana_pico(h, 3, False), 60)}")
    li = t("little_zona_mes")
    if li is not None and len(li):
        for z, lz in li.groupby("zona", sort=False):
            r_ = lz["L_sobre_lambdaW"].replace([np.inf, -np.inf], np.nan).median()
            print(f"  Little en {n(z)}: el censo observado {es(r_, 1.0)} λ·W (mediana entre meses)")

    titulo("E · Transiciones")
    m = t("transiciones_matriz")
    if m is not None:
        for o, mo in m.groupby("origen", sort=False):
            mo = mo.sort_values("probabilidad", ascending=False)
            mo = mo[mo["probabilidad"] >= 0.01].head(4)
            partes = [f"{'termina ahí' if d == FIN else 'pasa a ' + n(d)}: {cuanto(p)}"
                      for d, p in zip(mo["destino"], mo["probabilidad"])]
            print(f"  desde {n(o)}: " + "; ".join(partes))
    hu = t("transiciones_hueco")
    if hu is not None:
        print("  tiempo entre salir de una zona y entrar a la siguiente (transiciones más frecuentes):")
        for _, f in hu.head(8).iterrows():
            print(f"    {n(f['zona'])} → {n(f['siguiente'])}: típico {franja(f['p50'])}, p90 {franja(f['p90'])}; "
                  f"con solape {cuanto(f['p_solape'])}")
    rr = t("reconsultas_resumen")
    if rr is not None and len(rr):
        f = rr.iloc[0]
        print(f"  episodios seguidos de otro de la misma persona dentro de la ventana: {cuanto(f['proporcion'])}")
    rp = t("reconsultas_pares")
    if rp is not None:
        for _, f in rp.head(4).iterrows():
            print(f"    {n(f['zona_final'])} → {n(f['zona_inicial_siguiente'])}: hueco típico {franja(f['p50'] * 60)}")

    titulo("F · Relaciones")
    hh = t("rel_hora_entrada_salida")
    if hh is not None:
        for z, hz in hh.groupby("zona", sort=False):
            v = hz.set_index("h")["p50_por_hora_entrada"].dropna()
            if len(v) and v.min() > 0:
                print(f"  {n(z)}: según la hora de entrada, la mediana más alta ({rango_horas([int(v.idxmax())], 60)}) es "
                      f"{veces(v.max(), v.min())} la más baja ({rango_horas([int(v.idxmin())], 60)})")
    for nombre, txt in (("rel_censo", "censo al entrar"), ("rel_carga", "entradas recientes")):
        rc = t(nombre)
        if rc is None:
            continue
        grupos = ["zona", "variable"] if "variable" in rc.columns else ["zona"]
        for clave, g in rc.groupby(grupos, sort=False):
            g = g.sort_values("orden")
            z, var = (clave if isinstance(clave, tuple) else (clave,)) + ((None,) if len(grupos) == 1 else ())
            if len(g) < 2:
                continue
            etiqueta = f"{txt} ({var})" if var else txt
            print(f"  {n(z)}, {etiqueta}: en el cuantil más alto la mediana es "
                  f"{veces(g['p50'].iloc[-1], g['p50'].iloc[0])} la del más bajo")
    rd = t("rel_destino")
    if rd is not None:
        for z, dz in rd.groupby("zona", sort=False):
            dz = dz.sort_values("n", ascending=False).head(4)
            print(f"  {n(z)} según destino: " + "; ".join(f"{n(d)} {franja(p)}" for d, p in zip(dz["destino"], dz["p50"])))

    titulo("G · Tiempo")
    pm = t("perfil_mensual")
    if pm is not None and len(pm):
        for z, pz in pm.groupby("zona", sort=False):
            if pz["mes"].nunique() < 6:
                continue
            e = pz.set_index("mes")["entradas_por_dia"]
            print(f"  {n(z)}: mes con más entradas {MESES[int(e.idxmax()) - 1]}, con menos {MESES[int(e.idxmin()) - 1]} "
                  f"({veces(e.max(), e.min())})")

    titulo("H · Atributos")
    for p in sorted(t.carpeta.glob("atributo_*_duracion.csv")):
        a = pd.read_csv(p, dtype={"zona": str, "grupo": str})
        attr = a["atributo"].iloc[0] if len(a) else p.stem
        for z, az in a.groupby("zona", sort=False):
            az = az[az["grupo"] != "otros"]
            if len(az) < 2 or az["p50"].min() <= 0:
                continue
            alto, bajo = az.loc[az["p50"].idxmax()], az.loc[az["p50"].idxmin()]
            print(f"  {n(z)} por {attr}: el grupo {alto['grupo']} tiene mediana {veces(alto['p50'], bajo['p50'])} "
                  f"la del grupo {bajo['grupo']}")

    titulo("I · Cola larga")
    pa = t("pareto_zona")
    if pa is not None:
        for _, f in pa.iterrows():
            nombre = f["nombre"] if f["zona"] == "__episodios__" else n(f["zona"])
            print(f"  {nombre}: el 10 % más largo aporta {cuanto(f['p_horas_top_10pct'])} de las horas-paciente; "
                  f"el 1 % más largo, {cuanto(f['p_horas_top_1pct'])}")

    print("\nTodo lo de arriba se puede compartir: palabras, franjas y comparaciones cualitativas.\n")


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="python -m Cuellos_botella.resumen_seguro")
    ap.add_argument("--salida", default=None, help="carpeta de salidas (por defecto DATA_DIR/cuellos_botella_salidas)")
    a = ap.parse_args(argv)
    from .config import validar_salida
    carpeta = validar_salida(a.salida)
    if not (carpeta / "tablas").exists():
        print("No encontré la carpeta 'tablas'; corre primero python -m Cuellos_botella.")
        return 1
    resumir(Tablas(carpeta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
