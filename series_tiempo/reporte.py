"""Registro de figuras y tablas, y el reporte HTML autocontenido (mismo estilo que Cuellos_botella).
Cada figura lleva dos textos: qué muestra y cómo leerla."""
from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd
from plotly.offline import get_plotlyjs

from Cuellos_botella.reporte import CSS, MARCA_DERIVADO

CSS_EXTRA = """
.tri { display:grid; grid-template-columns:repeat(2,1fr); gap:12px; margin:8px 0 4px; }
.tri div { font-size:14px; color:var(--ink2); } .tri b { display:block; color:var(--ink); font-size:13px; margin-bottom:2px; }
.intro p { max-width:95ch; } .num { font-variant-numeric: tabular-nums; }
@media (max-width:800px) { .tri { grid-template-columns:1fr; } }
"""


@dataclass
class Fig:
    seccion: str
    titulo: str
    fig: object
    muestra: str
    leer: str


@dataclass
class Tabla:
    seccion: str
    nombre: str
    titulo: str
    df: pd.DataFrame
    texto: str
    mostrar: bool


@dataclass
class Registro:
    salida: Path
    piezas: list = field(default_factory=list)       # Fig y Tabla en orden de aparición
    avisos: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.salida = Path(self.salida)
        (self.salida / "tablas").mkdir(parents=True, exist_ok=True)

    def fig(self, seccion, titulo, fig, muestra, leer):
        self.piezas.append(Fig(seccion, titulo, fig, muestra, leer))

    def tabla(self, seccion, nombre, df, texto, titulo=None, mostrar=False):
        """Guarda la tabla en tablas/<nombre>.csv; con `mostrar` también la pone en el reporte."""
        df.to_csv(self.salida / "tablas" / f"{nombre}.csv", index=False, encoding="utf-8")
        self.piezas.append(Tabla(seccion, nombre, titulo or nombre, df, texto, mostrar))


def _id(t: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in t.lower()).strip("-")


def _tabla_html(df: pd.DataFrame) -> str:
    def celda(v):
        if isinstance(v, float):
            return f"<td class='num'>{v:,.3g}</td>" if abs(v) < 1e5 else f"<td class='num'>{v:,.0f}</td>"
        return f"<td>{html.escape(str(v))}</td>"
    cab = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    filas = "".join("<tr>" + "".join(celda(v) for v in fila) + "</tr>" for fila in df.itertuples(index=False))
    return f"<table><tr>{cab}</tr>{filas}</table>"


def escribir(reg: Registro, intro_html: str, origen: str) -> Path:
    orden = []
    for p in reg.piezas:
        if p.seccion not in orden:
            orden.append(p.seccion)
    idx = ["<nav class='card'><h3>Índice</h3><ol>"]
    cuerpo = []
    for s in orden:
        piezas = [p for p in reg.piezas if p.seccion == s and (isinstance(p, Fig) or p.mostrar)]
        idx.append(f"<li><a href='#{_id(s)}'>{html.escape(s)}</a><ol>")
        cuerpo.append(f"<h2 id='{_id(s)}'>{html.escape(s)}</h2>")
        for i, p in enumerate(piezas):
            ancla = f"{_id(s)}-{i}"
            idx.append(f"<li><a href='#{ancla}'>{html.escape(p.titulo)}</a></li>")
            if isinstance(p, Fig):
                div = p.fig.to_html(full_html=False, include_plotlyjs=False,
                                    config={"displaylogo": False, "responsive": True})
                cuerpo.append(
                    f"<div class='card' id='{ancla}'><h3>{html.escape(p.titulo)}</h3><div class='tri'>"
                    f"<div><b>Qué muestra</b>{html.escape(p.muestra)}</div>"
                    f"<div><b>Cómo leerla</b>{html.escape(p.leer)}</div></div>{div}</div>")
            else:
                cuerpo.append(f"<div class='card' id='{ancla}'><h3>{html.escape(p.titulo)}</h3>"
                              f"<p class='ley'>{html.escape(p.texto)}</p>{_tabla_html(p.df)}</div>")
        idx.append("</ol></li>")
    idx.append("</ol></nav>")

    avisos = ""
    if reg.avisos or reg.errores:
        items = [f"<li>{html.escape(a)}</li>" for a in reg.avisos]
        items += [f"<li>No se pudo generar: {html.escape(e)} (detalle en errores.log)</li>" for e in reg.errores]
        avisos = f"<div class='card avisos'><h3>Avisos</h3><ul>{''.join(items)}</ul></div>"

    tablas = [p for p in reg.piezas if isinstance(p, Tabla)]
    lista = "".join(f"<tr><td>{html.escape(t.seccion)}</td><td><a href='tablas/{html.escape(t.nombre)}.csv'>"
                    f"<code>{html.escape(t.nombre)}.csv</code></a></td><td>{html.escape(t.texto)}</td></tr>"
                    for t in tablas)
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{MARCA_DERIVADO}<!-- marca: scripts/check_no_data.py bloquea este archivo en git -->
<title>Series de tiempo</title><style>{CSS}{CSS_EXTRA}</style>
<script type="text/javascript">{get_plotlyjs()}</script></head><body><div class="wrap">
<h1>Series de tiempo: exploración para el pronóstico</h1>
<p class="sub">Generado {datetime.now():%Y-%m-%d %H:%M} desde <code>{html.escape(origen)}</code>.
Contiene información derivada de los datos del HUN (agregados): no lo compartas fuera del equipo ni lo subas a ninguna IA.</p>
<div class="card intro">{intro_html}</div>
{avisos}{''.join(idx)}{''.join(cuerpo)}
<h2 id="tablas">Tablas (CSV en la carpeta tablas/)</h2><div class="card"><table>
<tr><th>Sección</th><th>Archivo</th><th>Qué contiene</th></tr>{lista}</table></div>
</div></body></html>"""
    out = reg.salida / "reporte_series.html"
    out.write_text(doc, encoding="utf-8")
    return out
