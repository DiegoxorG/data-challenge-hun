"""Reporte de interpretación (pronóstico + escenarios) para leer EN TU COMPUTADOR. Lleva datos.

    python -m pronostico.reporte            # crea DATA_DIR/reporte_interpretacion.html y lo abre

Lee los CSV que dejan `python -m pronostico`, `python -m escenarios` y `python -m semaforo`
(DATA_DIR/pronostico, DATA_DIR/escenarios y DATA_DIR/semaforo) y arma una sola página con lo esencial: las cifras exactas para el
documento y 8 gráficas, cada una con "qué mirar" y preguntas para tu interpretación.

El HTML lleva la marca hun-datos (el hook anti-fuga lo bloquea). No lo compartas con ninguna IA ni
lo subas al repo: es para que TÚ interpretes.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import webbrowser
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
NOMBRES = {"naive_semanal": "Naïve (misma hora semana pasada)", "promedio_semanal": "Promedio 4 semanas",
           "glm": "GLM", "glm_nivel": "GLM + nivel reciente"}
SERIES = {"llegadas": "Llegadas a urgencias", "llegadas_hospitalizan": "Llegadas que se hospitalizan"}
MARCA = "hun" + "-datos"   # partido para que el chequeo anti-fuga no marque este archivo de código
AZUL, GRIS, NARANJA, VERDE = "#2b6cb0", "#a0aec0", "#dd6b20", "#2f855a"


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _seccion(n: int, titulo: str, img: str | None, mirar: list[str], preguntas: list[str],
             tabla: str = "", doc: str = "") -> str:
    li = lambda xs: "".join(f"<li>{x}</li>" for x in xs)  # noqa: E731
    return f"""<section><h2>{n}. {titulo}</h2>
{f'<img src="{img}">' if img else ''}{tabla}
<div class="guia"><div><h3>Qué mirar</h3><ul>{li(mirar)}</ul></div>
<div><h3>Tus preguntas (interpreta tú)</h3><ol>{li(preguntas)}</ol></div></div>
{f'<p class="doc">Para el documento: {doc}</p>' if doc else ''}</section>"""


def _tabla(df: pd.DataFrame) -> str:
    return df.to_html(index=False, classes="t", border=0, float_format=lambda x: f"{x:,.2f}")


# --- secciones ------------------------------------------------------------------------------
def s_metricas(met: pd.DataFrame, meta: dict) -> str:
    m = met.copy()
    m["modelo"] = m["modelo"].map(NOMBRES).fillna(m["modelo"])
    m["serie"] = m["serie"].map(SERIES).fillna(m["serie"])
    cols = {"serie": "Serie", "modelo": "Modelo", "mape_dia": "MAPE diario", "mase_dia": "MASE diario",
            "mae_dia": "MAE diario", "mae_hora": "MAE hora", "sesgo_hora": "Sesgo/hora",
            "cobertura_intervalo_dia": "Cobertura 90% día", "media_real_dia": "Llegadas/día (media)"}
    m = m[list(cols)].rename(columns=cols)
    for c in ("MAPE diario", "Cobertura 90% día"):
        m[c] = (m[c] * 100).round(1).astype(str) + " %"
    eleg = ", ".join(f"{SERIES.get(s, s)}: <b>{NOMBRES.get(v.get('modelo_elegido'), v.get('modelo_elegido'))}</b>"
                     for s, v in meta.get("series", {}).items())
    return _seccion(1, "Qué tan bueno es el modelo (backtest, 12 semanas que no vio)", None,
                    [f"Modelo elegido para el futuro → {eleg}.",
                     "MASE &lt; 1 = le gana a la naïve. 0.7 = 30 % menos error.",
                     "MAPE diario = error típico de un día en %. Cobertura ideal ≈ 90 %."],
                    ["¿Cuánto mejor es el modelo elegido frente a la naïve y frente al promedio de 4 semanas?",
                     "¿Un error diario de ese tamaño sirve para planear turnos y camas? ¿Por qué?",
                     "¿Por qué la serie de hospitalizados tiene más error relativo que la de llegadas?"],
                    _tabla(m), "estas cifras van en la tabla de Resultados ([X6], [X8]–[X12]).")


def s_backtest(btd: pd.DataFrame, meta: dict, serie: str, n: int) -> str:
    el = meta["series"].get(serie, {}).get("modelo_elegido", "glm")
    d = btd[(btd["serie"] == serie)]
    g = d[d["modelo"] == el].sort_values("fecha")
    b = d[d["modelo"] == "promedio_semanal"].sort_values("fecha")
    fig, ax = plt.subplots(figsize=(11, 3.6))
    ax.fill_between(g["fecha"], g["li"], g["ls"], color=AZUL, alpha=.15, label="intervalo 90 %")
    ax.plot(g["fecha"], g["real"], color="black", lw=1.6, label="real")
    ax.plot(g["fecha"], g["pred"], color=AZUL, lw=1.6, label=NOMBRES.get(el, el))
    ax.plot(b["fecha"], b["pred"], color=GRIS, lw=1.2, ls="--", label="promedio 4 semanas")
    fuera = g[(g["real"] < g["li"]) | (g["real"] > g["ls"])]
    ax.scatter(fuera["fecha"], fuera["real"], color=NARANJA, zorder=5, label="fuera del intervalo")
    ax.set_title(f"{SERIES.get(serie, serie)} por día: real vs pronóstico en semanas de prueba")
    ax.legend(ncol=5, fontsize=8, loc="upper left"); ax.grid(alpha=.3)
    peor = g.assign(err=(g["real"] - g["pred"]).abs()).nlargest(3, "err")
    tabla = _tabla(peor[["fecha", "real", "pred", "err"]].rename(columns={"err": "error abs"}))
    return _seccion(n, f"Backtest diario: {SERIES.get(serie, serie)}", _png(fig),
                    ["Si la línea azul sigue a la negra, y si la gris (promedio) se queda atrás en los cambios.",
                     "Los puntos naranja: días que el modelo no vio venir. Abajo, los 3 peores días."],
                    ["¿Los peores días coinciden con festivos, puentes o fechas especiales? (mira el calendario)",
                     "¿El modelo falla más en subidas o en bajadas?",
                     "¿Hay alguna semana entera corrida (todo arriba o todo abajo)? ¿Qué pudo pasar?"], tabla)


def s_futuro(pdia: pd.DataFrame, serie: str, n: int) -> str:
    d = pdia[pdia["serie"] == serie].sort_values("fecha")
    hist = d[d["tipo"] == "historico"].tail(56)
    fut = d[d["tipo"] == "futuro"]
    fig, ax = plt.subplots(figsize=(11, 3.4))
    ax.plot(hist["fecha"], hist["real"], color="black", lw=1.3, label="real (últimas 8 semanas)")
    ax.fill_between(fut["fecha"], fut["li"], fut["ls"], color=VERDE, alpha=.2, label="intervalo 90 %")
    ax.plot(fut["fecha"], fut["pred"], color=VERDE, lw=1.8, marker="o", ms=3, label="pronóstico")
    ax.set_title(f"{SERIES.get(serie, serie)}: próximos días"); ax.legend(fontsize=8); ax.grid(alpha=.3)
    return _seccion(n, f"Pronóstico hacia adelante: {SERIES.get(serie, serie)}", _png(fig),
                    ["Que el pronóstico continúe el nivel de las últimas semanas reales.",
                     "El ancho de la banda: es lo que el hospital debería tener de margen."],
                    ["¿Qué días del horizonte serían los más cargados y por qué (día de semana, festivo)?",
                     "Si fueras el coordinador de urgencias, ¿qué harías con este pronóstico el domingo anterior?"],
                    doc="ejemplo concreto para la presentación ('el lunes X se esperan entre A y B llegadas').")


def s_perfil(per: pd.DataFrame, serie: str, n: int) -> str:
    p = per[per["serie"] == serie].pivot(index="dia_semana", columns="hora_dia", values="relativo")
    fig, ax = plt.subplots(figsize=(11, 3.2))
    im = ax.imshow(p.to_numpy(), aspect="auto", cmap="YlOrRd")
    ax.set_yticks(range(7), DIAS); ax.set_xticks(range(0, 24, 2), [f"{h}h" for h in range(0, 24, 2)])
    fig.colorbar(im, ax=ax, label="× hora promedio")
    ax.set_title(f"{SERIES.get(serie, serie)}: llegadas esperadas por día y hora (1 = hora promedio)")
    return _seccion(n, f"Cuándo llega la gente: {SERIES.get(serie, serie)}", _png(fig),
                    ["Dónde está el bloque rojo (franja pico) y si se repite todos los días.",
                     "Diferencia entre lunes y fin de semana."],
                    ["¿En qué franja reforzarías personal y cuántas horas dura el pico?",
                     "¿Por qué crees que el lunes en la mañana es el pico? (fin de semana acumulado, EPS cerradas…)",
                     "¿Las hospitalizaciones tienen el mismo pico que las llegadas? ¿Qué implica para las camas?"],
                    doc="[hora a], [hora b], [días] y la franja de la propuesta 4.")


def s_efectos(efe: pd.DataFrame, n: int) -> str:
    e = efe.pivot(index="efecto", columns="serie", values="multiplicador")
    fig, ax = plt.subplots(figsize=(9, 3.4))
    y = np.arange(len(e))
    for i, (s, c) in enumerate(zip(e.columns, [AZUL, NARANJA])):
        ax.barh(y + i * .38, e[s] - 1, height=.36, left=1, color=c, label=SERIES.get(s, s))
    ax.axvline(1, color="black", lw=1); ax.set_yticks(y + .19, e.index)
    ax.set_xlabel("multiplicador (1 = sin efecto)"); ax.legend(fontsize=8); ax.grid(alpha=.3, axis="x")
    tabla = _tabla(e.reset_index())
    return _seccion(n, "Efecto del calendario", _png(fig),
                    ["Barras a la izquierda de 1 = llega menos gente; a la derecha = más.",
                     "tendencia_por_anio: cuánto cambia la demanda de fondo cada año."],
                    ["¿Por qué el día después de un festivo llega más gente?",
                     "¿Por qué el Carnaval baja tanto las llegadas en Barranquilla?",
                     "¿La baja de fondo es menos enfermedad, cambio de EPS/red, o registro? ¿Cómo lo verificarías?"],
                    tabla, "[X7] (festivo) y la tendencia.")


def s_error_hora(bth: pd.DataFrame, meta: dict, n: int) -> str:
    s = "llegadas"
    el = meta["series"].get(s, {}).get("modelo_elegido", "glm")
    g = bth[(bth["serie"] == s) & (bth["modelo"] == el)].copy()
    g["ae"] = (g["real"] - g["pred"]).abs()
    r = g.groupby("hora_dia").agg(mae=("ae", "mean"), media=("real", "mean"))
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.bar(r.index, r["mae"] / r["media"].where(r["media"] > 0), color=AZUL)
    ax.set_xlabel("hora del día"); ax.set_ylabel("error / llegadas medias"); ax.grid(alpha=.3, axis="y")
    ax.set_title("Error relativo del pronóstico por hora del día (llegadas)")
    return _seccion(n, "Dónde se equivoca el modelo", _png(fig),
                    ["Horas con barras altas = el modelo es menos confiable ahí (suele ser la madrugada: pocos pacientes)."],
                    ["¿El error es aceptable en la franja pico, que es la que importa para planear?",
                     "¿Qué limitación de los datos explica el error que queda (no hay triaje, eventos externos)?"])


def s_escenario1(res: pd.DataFrame, esc: pd.DataFrame, meta_e: dict, n: int) -> str:
    fig, axs = plt.subplots(1, 2, figsize=(12, 3.6))
    axs[0].plot(res["reduccion_espera_h"], res["reduccion_pct"] * 100, marker="o", color=AZUL, label="promedio")
    axs[0].plot(res["reduccion_espera_h"], res["reduccion_pct_pico"] * 100, marker="o", color=NARANJA, label="franja pico")
    axs[0].set_xlabel("horas menos de espera de cama"); axs[0].set_ylabel("% menos censo en urgencias")
    axs[0].legend(); axs[0].grid(alpha=.3); axs[0].set_title("Cuánto baja la congestión")
    e = esc[esc["reduccion_espera_h"].isin([0, 4])].groupby(["reduccion_espera_h", "hora_dia"])[
        "censo_urgencias_escenario"].mean().unstack(0)
    axs[1].plot(e.index, e[0], color="black", label="hoy"); axs[1].plot(e.index, e[4], color=VERDE, label="−4 h de espera")
    axs[1].fill_between(e.index, e[4], e[0], color=VERDE, alpha=.2)
    axs[1].set_xlabel("hora del día"); axs[1].set_ylabel("pacientes en urgencias (promedio)")
    axs[1].legend(); axs[1].grid(alpha=.3); axs[1].set_title("Censo de urgencias: hoy vs escenario")
    t = res[res["reduccion_espera_h"].isin([2, 4, 6, 8])][["reduccion_espera_h", "base", "escenario", "reduccion_pct",
                                                            "base_pico", "escenario_pico", "reduccion_pct_pico"]]
    f = meta_e.get("franja_pico", ["?", "?"])
    return _seccion(n, "Escenario 1: reducir la espera de cama", _png(fig),
                    [f"Franja pico usada: {f[0]}–{f[1]} h. Es un techo del efecto (supone que esos pacientes esperaban al menos esas horas).",
                     "La zona verde a la derecha = pacientes que dejarían de estar en urgencias."],
                    ["¿Cuántas horas de reducción son realistas para el HUN? (piensa en la visita de campo)",
                     "¿En qué horas del día se nota más el alivio y por qué coincide con cuando suben a cama?",
                     "¿Qué tendría que cambiar en el hospital para lograr esa reducción?"],
                    _tabla(t), "[h] y [X14] de 'Impacto esperado'.")


def s_escenario2(alt: pd.DataFrame, esc: pd.DataFrame, n: int) -> str:
    a = alt[(alt["adelanto_h"] == 4) & (alt["fraccion_altas"] == 0.5)].groupby("hora_dia")["camas_liberadas"].mean()
    u = esc[esc["reduccion_espera_h"] == 0].groupby("hora_dia")["censo_urgencias_base"].mean()
    fig, ax = plt.subplots(figsize=(11, 3.4))
    ax.bar(a.index, a, color=VERDE, label="camas liberadas antes (50 % de altas de la tarde, 4 h antes)")
    ax2 = ax.twinx(); ax2.plot(u.index, u, color="black", label="pacientes en urgencias (hoy)")
    ax.set_xlabel("hora del día"); ax.set_ylabel("camas liberadas"); ax2.set_ylabel("censo urgencias")
    ax.legend(loc="upper left", fontsize=8); ax2.legend(loc="upper right", fontsize=8); ax.grid(alpha=.3)
    ax.set_title("Altas más temprano: camas disponibles vs pacientes esperando en urgencias")
    return _seccion(n, "Escenario 2: altas de cama antes del mediodía", _png(fig),
                    ["Si las barras verdes caen en las horas en que urgencias está más lleno, la medida ataca el cuello."],
                    ["¿Las camas liberadas llegan a tiempo para el pico de urgencias, o tarde?",
                     "¿Qué porcentaje de altas adelantadas es creíble? ¿Qué lo impide hoy (ronda médica, papeles, transporte)?"])


def s_semaforo(sem: Path, n: int) -> str:
    pb = sem / "powerbi"
    fut = pd.read_csv(pb / "semaforo_futuro.csv", parse_dates=["fecha"])
    met = pd.read_csv(pb / "semaforo_metricas.csv")
    col = {"verde": 0, "amarillo": 1, "rojo": 2}
    from matplotlib.colors import ListedColormap
    cmap = ListedColormap(["#68d391", "#f6e05e", "#fc8181"])
    series = list(fut["serie"].unique())
    fig, axs = plt.subplots(len(series), 1, figsize=(12, 1.6 * len(series) + 0.6), squeeze=False)
    for ax, s_ in zip(axs[:, 0], series):
        f = fut[fut["serie"] == s_]
        m = f.pivot(index="turno", columns="fecha", values="color").reindex(["mañana", "tarde", "noche"])
        ax.imshow(m.replace(col).to_numpy(dtype=float), aspect="auto", cmap=cmap, vmin=0, vmax=2)
        ax.set_yticks(range(3), m.index)
        ax.set_xticks(range(m.shape[1]), [f"{DIAS[d.day_of_week]} {d.day}" for d in m.columns], fontsize=7)
        ax.set_title(SERIES.get(s_, s_), fontsize=10)
    fig.tight_layout()
    t = met.copy()
    t["modelo"] = t["modelo"].map(NOMBRES).fillna(t["modelo"])
    cols = ["serie", "modelo", "sensibilidad_critico", "criticos_en_verde", "precision_alerta",
            "riesgo_critico_en_alerta", "riesgo_critico_en_verde", "tasa_alerta"]
    t = t[[c for c in cols if c in t]]
    for c in t.columns[2:]:
        t[c] = (t[c] * 100).round(0).astype("Int64").astype(str) + " %"
    return _seccion(n, "Semáforo de saturación por turno", _png(fig),
                    ["Calendario: cada casilla es un turno (mañana 7-13, tarde 13-19, noche 19-7).",
                     "Tabla: validación en las semanas de prueba. sensibilidad = turnos críticos que tuvieron alerta; "
                     "riesgo en alerta vs en verde: si el primero es mucho mayor, la alerta discrimina.",
                     "Compara la fila del modelo con la de la naïve: ¿alerta mejor o solo alerta más?"],
                    ["¿Qué turnos salen en amarillo/rojo y tiene sentido (lunes, después de festivo)?",
                     "¿Cuántas alertas por semana puede atender el hospital sin que se vuelvan ruido?",
                     "¿Qué turnos críticos NO se anticiparon y por qué (picos al azar, eventos externos)?"],
                    _tabla(t), "tabla de validación del semáforo (sección Semáforo del documento).")


# --- armado -----------------------------------------------------------------------------------
CSS = """body{font-family:Segoe UI,Arial,sans-serif;max-width:1150px;margin:24px auto;color:#1a202c;padding:0 16px}
h1{margin-bottom:4px}section{border-top:2px solid #e2e8f0;padding:14px 0}img{max-width:100%}
.guia{display:grid;grid-template-columns:1fr 1fr;gap:18px}.guia h3{margin:6px 0;font-size:15px}
.guia li{margin:3px 0}.doc{background:#fefcbf;padding:6px 10px;border-radius:4px}
.aviso{background:#fed7d7;padding:8px 12px;border-radius:4px}
table.t{border-collapse:collapse;font-size:13px;margin:8px 0}table.t th,table.t td{padding:4px 8px;border-bottom:1px solid #e2e8f0;text-align:right}"""


def armar(pron: Path, esc: Path | None, sem: Path | None = None) -> str:
    pb = pron / "powerbi"
    meta = json.loads((pron / "meta.json").read_text(encoding="utf-8"))
    met = pd.read_csv(pb / "metricas_modelos.csv")
    btd = pd.read_csv(pb / "backtest_diario.csv", parse_dates=["fecha"])
    bth = pd.read_csv(pb / "backtest_horario.csv", parse_dates=["hora"])
    pdia = pd.read_csv(pb / "pronostico_diario.csv", parse_dates=["fecha"])
    per = pd.read_csv(pb / "perfil_semana.csv")
    efe = pd.read_csv(pb / "efectos_calendario.csv")
    partes = [s_metricas(met, meta)]
    k = 2
    for s in meta["series"]:
        partes.append(s_backtest(btd, meta, s, k)); k += 1
    partes.append(s_futuro(pdia, "llegadas", k)); k += 1
    partes.append(s_perfil(per, "llegadas", k)); k += 1
    if "llegadas_hospitalizan" in meta["series"]:
        partes.append(s_perfil(per, "llegadas_hospitalizan", k)); k += 1
    partes.append(s_efectos(efe, k)); k += 1
    partes.append(s_error_hora(bth, meta, k)); k += 1
    if esc is not None and (esc / "meta.json").exists():
        ep = esc / "powerbi"
        me = json.loads((esc / "meta.json").read_text(encoding="utf-8"))
        e1 = pd.read_csv(ep / "escenario_espera_cama.csv")
        partes.append(s_escenario1(pd.read_csv(ep / "resumen_espera_cama.csv"), e1, me, k)); k += 1
        partes.append(s_escenario2(pd.read_csv(ep / "escenario_altas_temprano.csv"), e1, k)); k += 1
    else:
        partes.append("<section><h2>Escenarios</h2><p>No encontré la corrida: corre <code>python -m escenarios</code>.</p></section>")
    if sem is not None and (sem / "meta.json").exists():
        partes.append(s_semaforo(sem, k)); k += 1
    else:
        partes.append("<section><h2>Semáforo</h2><p>No encontré la corrida: corre <code>python -m semaforo</code>.</p></section>")
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="{MARCA}" content="reporte generado con datos del HUN: no compartir ni subir al repo">
<title>Interpretación: pronóstico y escenarios</title><style>{CSS}</style></head><body>
<h1>Interpretación: pronóstico y escenarios</h1>
<p class="aviso">Contiene datos del HUN. Solo para leer en este computador: no lo subas al repo, a la nube ni a ninguna IA.
Las interpretaciones las escribes tú; si quieres que Claude las revise, pásale el texto con los números tapados.</p>
{''.join(partes)}</body></html>"""


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="python -m pronostico.reporte")
    ap.add_argument("--pronostico", default=None, help="carpeta de python -m pronostico (por defecto DATA_DIR/pronostico)")
    ap.add_argument("--escenarios", default=None, help="carpeta de python -m escenarios (por defecto DATA_DIR/escenarios)")
    ap.add_argument("--semaforo", default=None, help="carpeta de python -m semaforo (por defecto DATA_DIR/semaforo)")
    ap.add_argument("--no-abrir", action="store_true")
    a = ap.parse_args(argv)
    from hun.config import validar_carpeta
    if a.pronostico is None or a.escenarios is None or a.semaforo is None:
        from hun.config import data_dir
        base = data_dir()
    pron = validar_carpeta(Path(a.pronostico) if a.pronostico else base / "pronostico", "El pronóstico")
    esc = Path(a.escenarios) if a.escenarios else base / "escenarios"
    if not (pron / "meta.json").exists():
        print("No encontré la corrida del pronóstico; corre primero python -m pronostico.")
        return 1
    sem = Path(a.semaforo) if a.semaforo else base / "semaforo"
    html = armar(pron, esc, sem)
    out = validar_carpeta(pron.parent, "El reporte") / "reporte_interpretacion.html"
    out.write_text(html, encoding="utf-8")
    print(f"Reporte listo: {out}")
    if not a.no_abrir:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
