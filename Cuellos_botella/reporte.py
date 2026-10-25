"""Reporte HTML autocontenido: índice, avisos, figuras con su leyenda y lista de tablas.
plotly.js va embebido una sola vez, así el archivo abre sin internet."""
from __future__ import annotations

import html
from datetime import datetime
from itertools import groupby
from pathlib import Path

from plotly.offline import get_plotlyjs

from .comun import Registro
from .config import Config

# Marca para que scripts/check_no_data.py bloquee el reporte en git. Se arma por partes para
# que este archivo de código no lleve la marca literal (si no, el hook lo bloquearía a él).
MARCA_DERIVADO = '<meta name="hun-' + 'datos" content="derivado">'

CSS = """
:root { color-scheme: light; --bg:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
        --line:#e1e0d9; --accent:#2a78d6; --warn:#fab219; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }
.wrap { max-width:1180px; margin:0 auto; padding:24px 16px 80px; }
h1 { font-size:26px; margin:0 0 4px; } h2 { font-size:20px; margin:48px 0 8px; padding-top:8px; border-top:1px solid var(--line); }
h3 { font-size:16px; margin:0 0 6px; }
.sub { color:var(--ink2); margin:0 0 20px; }
.card { background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:16px; margin:16px 0; }
.ley { color:var(--ink2); font-size:14px; margin:4px 0 8px; max-width:90ch; }
nav ol { columns:2; column-gap:32px; padding-left:20px; } nav li { margin:2px 0; break-inside:avoid; }
nav ol ol { columns:1; font-size:14px; }
a { color:var(--accent); text-decoration:none; } a:hover { text-decoration:underline; }
.avisos li { margin:4px 0; } .avisos { border-left:4px solid var(--warn); }
table { border-collapse:collapse; width:100%; font-size:14px; } td, th { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); vertical-align:top; }
code { font-size:13px; background:#f0efec; padding:1px 4px; border-radius:4px; }
@media (max-width:700px) { nav ol { columns:1; } }
"""


def _id(texto: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in texto.lower()).strip("-")


def escribir(reg: Registro, cfg: Config, entrada: str) -> Path:
    figs = sorted(reg.figuras, key=lambda f: f.seccion)   # orden A..I, estable dentro de cada sección
    secciones = [(s, list(g)) for s, g in groupby(figs, key=lambda f: f.seccion)]

    idx = ["<nav class='card'><h3>Índice</h3><ol>"]
    for s, fs in secciones:
        idx.append(f"<li><a href='#{_id(s)}'>{html.escape(s)}</a><ol>")
        idx += [f"<li><a href='#{_id(s)}-{i}'>{html.escape(f.titulo)}</a></li>" for i, f in enumerate(fs)]
        idx.append("</ol></li>")
    idx.append("<li><a href='#tablas'>Tablas de métricas (CSV)</a></li></ol></nav>")

    avisos = ""
    if reg.avisos or reg.errores:
        items = [f"<li>{html.escape(a)}</li>" for a in reg.avisos]
        items += [f"<li>No se pudo generar: {html.escape(e)} (detalle en errores.log)</li>" for e in reg.errores]
        avisos = f"<div class='card avisos'><h3>Avisos de calidad de datos</h3><ul>{''.join(items)}</ul></div>"

    params = [("persona / zona / inicio / fin", f"{cfg.persona} / {cfg.zona} / {cfg.inicio} / {cfg.fin}"),
              ("episodios", f"columna {cfg.caso}" if cfg.caso else f"umbral {cfg.umbral_min:g} min"),
              ("recorte al inicio de la zona siguiente", "sí" if cfg.recortar_al_siguiente else "no"),
              ("zonas excluidas", ", ".join(cfg.zonas_excluir) or "ninguna"),
              ("rango de fechas configurado", f"{cfg.desde or '—'} a {cfg.hasta or '—'}"),
              ("capacidades de referencia", "configuradas" if cfg.capacidades else "no configuradas"),
              ("atributos", ", ".join(a.columna for a in cfg.atributos) or "ninguno")]
    tabla_cfg = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>" for k, v in params)

    cuerpo = []
    for s, fs in secciones:
        cuerpo.append(f"<h2 id='{_id(s)}'>{html.escape(s)}</h2>")
        for i, f in enumerate(fs):
            div = f.fig.to_html(full_html=False, include_plotlyjs=False,
                                config={"displaylogo": False, "responsive": True})
            cuerpo.append(f"<div class='card' id='{_id(s)}-{i}'><h3>{html.escape(f.titulo)}</h3>"
                          f"<p class='ley'>{html.escape(f.leyenda)}</p>{div}</div>")

    filas = "".join(f"<tr><td>{html.escape(s)}</td><td><a href='tablas/{n}.csv'><code>{n}.csv</code></a></td>"
                    f"<td>{html.escape(d)}</td></tr>" for s, n, d in sorted(reg.tablas, key=lambda t: t[0]))
    tablas = (f"<h2 id='tablas'>Tablas de métricas (CSV)</h2><div class='card'><table>"
              f"<tr><th>Sección</th><th>Archivo</th><th>Qué contiene</th></tr>{filas}</table></div>")

    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{MARCA_DERIVADO}<!-- marca: scripts/check_no_data.py bloquea este archivo en git -->
<title>Cuellos de botella</title><style>{CSS}</style>
<script type="text/javascript">{get_plotlyjs()}</script></head><body><div class="wrap">
<h1>Cuellos de botella: vistas exploratorias</h1>
<p class="sub">Generado {datetime.now():%Y-%m-%d %H:%M} desde <code>{html.escape(Path(entrada).name)}</code>.
Este reporte muestra datos, no conclusiones: cada figura explica qué muestra y cómo leerla.
Contiene información derivada de los datos de entrada; no lo compartas fuera del equipo ni lo subas a ninguna IA.</p>
<div class="card"><h3>Configuración</h3><table>{tabla_cfg}</table></div>
{avisos}{''.join(idx)}{''.join(cuerpo)}{tablas}</div></body></html>"""
    out = reg.salida / "reporte.html"
    out.write_text(doc, encoding="utf-8")
    return out
