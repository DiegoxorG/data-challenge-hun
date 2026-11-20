"""Modelos de pronóstico de llegadas por hora y su evaluación.

Tres modelos, del más simple al principal:
  naive_semanal     la misma hora de la semana pasada (la línea base que hay que ganar)
  promedio_semanal  promedio de esa hora de la semana en las últimas 4 semanas
  glm               regresión de conteos (Poisson, con intervalos de binomial negativa si hay
                    sobredispersión) con hora de la semana, festivos y temporadas, estacionalidad
                    anual y tendencia

¿Por qué un GLM y no SARIMA/Prophet? Los conteos por hora son pequeños y nunca negativos (Poisson),
el patrón dominante es la hora de la semana (168 h, demasiado largo para un SARIMA horario) y cada
coeficiente se lee como "multiplica las llegadas por X". Se explica en una frase ante el jurado.

Evaluación: backtest rodante. Se entrena con todo lo anterior a un corte, se pronostica la
semana siguiente, se avanza una semana y se repite. Solo entran horas `completo`.
No toca la base: trabaja sobre las series que deja `python -m series_tiempo`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import PoissonRegressor

H_SEMANA = 168
SEMANAS_PROMEDIO = 4
NIVEL_INTERVALO = 0.90
# Columnas de calendario de series_tiempo.calendario que entran como variables
CALENDARIO = ["festivo", "despues_de_festivo", "puente", "semana_santa", "carnaval", "navidad_anio_nuevo"]
MODELOS = ["naive_semanal", "promedio_semanal", "glm", "glm_nivel"]
MIN_DIAS_ANUAL = 730       # estacionalidad anual solo con 2+ años de historia
MIN_DIAS_TENDENCIA = 180


# --- variables -------------------------------------------------------------------------
def variables(horas: pd.DatetimeIndex, cal: pd.DataFrame, t0: pd.Timestamp) -> pd.DataFrame:
    """Matriz de diseño para cada hora. `cal` = calendario diario (índice fecha) con CALENDARIO.

    - hora de la semana (168 dummies): el ciclo día × hora completo
    - festivo × hora del día: un festivo se parece a un domingo, pero con su propio perfil
    - resto del calendario (puente, Semana Santa, Carnaval, fin de año, día después de festivo)
    - estacionalidad anual con 2 armónicos de Fourier (suave, no 12 dummies de mes)
    - tendencia lineal en años desde t0
    """
    idx = pd.DatetimeIndex(horas)
    how = idx.dayofweek * 24 + idx.hour
    X = {f"how_{k:03d}": (how == k).astype(float) for k in range(H_SEMANA)}
    c = cal.reindex(idx.normalize())
    for col in CALENDARIO:
        v = c[col].fillna(False).astype(bool).to_numpy() if col in c else np.zeros(len(idx), bool)
        X[f"cal_{col}"] = v.astype(float)
    fest = X["cal_festivo"]
    for h in range(24):
        X[f"festivo_h{h:02d}"] = fest * (idx.hour == h)
    doy = idx.dayofyear.to_numpy() / 365.25
    for k in (1, 2):
        X[f"anual_sin{k}"] = np.sin(2 * np.pi * k * doy)
        X[f"anual_cos{k}"] = np.cos(2 * np.pi * k * doy)
    X["tendencia_anios"] = ((idx - t0) / pd.Timedelta(days=365.25)).to_numpy(dtype=float)
    return pd.DataFrame(X, index=idx)


# --- GLM -------------------------------------------------------------------------------
@dataclass
class Glm:
    reg: PoissonRegressor
    columnas: list[str]
    t0: pd.Timestamp
    alpha_nb: float          # 0 = Poisson; > 0 = binomial negativa Var = mu + alpha mu²
    dispersion: float        # Pearson chi² / gl: ~1 Poisson, > 1 sobredispersión
    coef: pd.Series = field(default=None)

    def media(self, horas, cal) -> np.ndarray:
        X = variables(horas, cal, self.t0)[self.columnas]
        return self.reg.predict(X.to_numpy())

    def intervalo(self, mu: np.ndarray, nivel: float = NIVEL_INTERVALO) -> tuple[np.ndarray, np.ndarray]:
        a = (1 - nivel) / 2
        if self.alpha_nb > 1e-6:
            n = 1 / self.alpha_nb
            p = n / (n + mu)
            return stats.nbinom.ppf(a, n, p), stats.nbinom.ppf(1 - a, n, p)
        return stats.poisson.ppf(a, mu), stats.poisson.ppf(1 - a, mu)


def ajustar_glm(y: pd.Series, cal: pd.DataFrame, penalizacion: float = 1e-4) -> Glm:
    """Ajusta el GLM con las horas válidas de `y` (sin NaN). Penalización mínima solo para que
    las dummies + intercepto queden identificadas."""
    y = y.dropna()
    t0 = y.index.min()
    X = variables(y.index, cal, t0)
    # Columnas de calendario que nunca ocurren en el entrenamiento no aportan
    cols = [c for c in X.columns if not (c.startswith(("cal_", "festivo_h")) and X[c].sum() == 0)]
    span = (y.index.max() - y.index.min()).days
    # Con menos de 2 años, la estacionalidad anual se confunde con la tendencia (y la inventa):
    # se deja fuera. Con menos de 6 meses tampoco se estima tendencia.
    if span < MIN_DIAS_ANUAL:
        cols = [c for c in cols if not c.startswith("anual_")]
    if span < MIN_DIAS_TENDENCIA:
        cols = [c for c in cols if c != "tendencia_anios"]
    reg = PoissonRegressor(alpha=penalizacion, max_iter=3000, tol=1e-6)
    reg.fit(X[cols].to_numpy(), y.to_numpy())
    mu = reg.predict(X[cols].to_numpy())
    gl = max(len(y) - len(cols) - 1, 1)
    disp = float(np.sum((y.to_numpy() - mu) ** 2 / np.maximum(mu, 1e-9)) / gl)
    # Binomial negativa NB2 por momentos: E[(y-mu)² - mu] = alpha mu²
    alpha = float(max(np.sum((y.to_numpy() - mu) ** 2 - mu) / np.sum(mu ** 2), 0.0)) if disp > 1.1 else 0.0
    coef = pd.Series(reg.coef_, index=cols)
    return Glm(reg=reg, columnas=cols, t0=t0, alpha_nb=alpha, dispersion=disp, coef=coef)


# --- líneas base -------------------------------------------------------------------------
def naive_semanal(y: pd.Series, horas: pd.DatetimeIndex, corte: pd.Timestamp) -> np.ndarray:
    """Para cada hora futura, el último valor observado (antes del corte) en esa misma hora de
    la semana. Con horizonte de una semana es exactamente 'la semana pasada'."""
    hist = y[y.index < corte].dropna()
    ult = hist.groupby(hist.index.dayofweek * 24 + hist.index.hour).last()
    how = horas.dayofweek * 24 + horas.hour
    return ult.reindex(how).to_numpy(dtype=float)


def promedio_semanal(y: pd.Series, horas: pd.DatetimeIndex, corte: pd.Timestamp,
                     semanas: int = SEMANAS_PROMEDIO) -> np.ndarray:
    hist = y[(y.index < corte) & (y.index >= corte - pd.Timedelta(weeks=semanas))].dropna()
    m = hist.groupby(hist.index.dayofweek * 24 + hist.index.hour).mean()
    how = horas.dayofweek * 24 + horas.hour
    return m.reindex(how).to_numpy(dtype=float)


# --- backtest ----------------------------------------------------------------------------
def cortes_backtest(y: pd.Series, semanas: int, min_entrenamiento_dias: int = 180) -> list[pd.Timestamp]:
    """Cortes semanales hacia atrás desde el final de los datos válidos. Solo cortes con al menos
    `min_entrenamiento_dias` de historia y con la semana de prueba completa."""
    v = y.dropna()
    if v.empty:
        return []
    fin = v.index.max().normalize() + pd.Timedelta(days=1)
    cortes = []
    for k in range(1, semanas + 1):
        c = fin - pd.Timedelta(weeks=k)
        prueba = y[(y.index >= c) & (y.index < c + pd.Timedelta(weeks=1))]
        if len(prueba) == H_SEMANA and prueba.notna().all() and (c - v.index.min()).days >= min_entrenamiento_dias:
            cortes.append(c)
    return sorted(cortes)


def nivel_reciente(y: pd.Series, g: "Glm", cal: pd.DataFrame, corte: pd.Timestamp,
                   semanas: int = SEMANAS_PROMEDIO) -> float:
    """Cociente real / ajustado del GLM en las últimas `semanas` antes del corte. Corrige el nivel
    cuando la demanda reciente se aparta de lo que el GLM aprendió con toda la historia (la tendencia
    lineal no sigue bien los cambios recientes). Acotado a [0.5, 1.5] para que un hueco de registro
    no lo dispare."""
    v = y[(y.index < corte) & (y.index >= corte - pd.Timedelta(weeks=semanas))].dropna()
    if v.empty:
        return 1.0
    mu = g.media(v.index, cal)
    return float(np.clip(v.sum() / max(mu.sum(), 1e-9), 0.5, 1.5))


def backtest(y: pd.Series, cal: pd.DataFrame, semanas: int = 12) -> pd.DataFrame:
    """Pronóstico de cada semana de prueba con los cuatro modelos. Devuelve una fila por
    hora × modelo con real, pred y el corte. Los intervalos se calibran después (`calibrar`)."""
    filas = []
    for c in cortes_backtest(y, semanas):
        horas = pd.date_range(c, periods=H_SEMANA, freq="h")
        real = y.reindex(horas).to_numpy(dtype=float)
        g = ajustar_glm(y[y.index < c], cal)
        mu = g.media(horas, cal)
        preds = {"naive_semanal": naive_semanal(y, horas, c),
                 "promedio_semanal": promedio_semanal(y, horas, c),
                 "glm": mu,
                 "glm_nivel": mu * nivel_reciente(y, g, cal, c)}
        for m, p in preds.items():
            filas.append(pd.DataFrame({"hora": horas, "corte": c, "modelo": m, "real": real, "pred": p}))
    if not filas:
        return pd.DataFrame(columns=["hora", "corte", "modelo", "real", "pred", "li", "ls"])
    return calibrar(pd.concat(filas, ignore_index=True))


# --- intervalos calibrados con errores fuera de muestra ------------------------------------
def alpha_empirico(real, pred) -> float:
    """Dispersión NB2 (Var = mu + alpha mu²) estimada con errores de pronóstico reales, no con el
    ajuste: así el intervalo incluye también el error de nivel del modelo."""
    r, p = np.asarray(real, float), np.asarray(pred, float)
    ok = np.isfinite(r) & np.isfinite(p) & (p > 0)
    if ok.sum() < 5:
        return 0.0
    r, p = r[ok], p[ok]
    return float(max(np.sum((r - p) ** 2 - p) / np.sum(p ** 2), 0.0))


def intervalo_nb(mu, alpha: float, nivel: float = NIVEL_INTERVALO) -> tuple[np.ndarray, np.ndarray]:
    mu = np.maximum(np.asarray(mu, dtype=float), 1e-9)
    a = (1 - nivel) / 2
    if alpha > 1e-6:
        n = 1 / alpha
        q = n / (n + mu)
        return stats.nbinom.ppf(a, n, q), stats.nbinom.ppf(1 - a, n, q)
    return stats.poisson.ppf(a, mu), stats.poisson.ppf(1 - a, mu)


def _diario(bt: pd.DataFrame) -> pd.DataFrame:
    return (bt.assign(dia=bt["hora"].dt.normalize())
              .groupby(["modelo", "corte", "dia"], sort=False)[["real", "pred"]].sum(min_count=1).reset_index())


def calibrar(bt: pd.DataFrame) -> pd.DataFrame:
    """Intervalos horarios de cada semana de prueba con la dispersión estimada en las OTRAS semanas
    (dejar una fuera): la cobertura que se reporta es honesta, no se mide con lo que se ajustó."""
    bt = bt.copy()
    bt["li"], bt["ls"] = np.nan, np.nan
    for m, g in bt.groupby("modelo"):
        for c in g["corte"].unique():
            otras = g[g["corte"] != c]
            a = alpha_empirico(otras["real"], otras["pred"]) if len(otras) else 0.0
            idx = g.index[g["corte"] == c]
            li, ls = intervalo_nb(bt.loc[idx, "pred"], a)
            bt.loc[idx, "li"], bt.loc[idx, "ls"] = li, ls
    return bt


def diario_calibrado(bt: pd.DataFrame) -> pd.DataFrame:
    """Totales diarios del backtest con intervalo diario calibrado (dejar una semana fuera)."""
    d = _diario(bt)
    d["li"], d["ls"] = np.nan, np.nan
    for m, g in d.groupby("modelo"):
        for c in g["corte"].unique():
            otras = g[g["corte"] != c]
            a = alpha_empirico(otras["real"], otras["pred"]) if len(otras) else 0.0
            idx = g.index[g["corte"] == c]
            li, ls = intervalo_nb(d.loc[idx, "pred"], a)
            d.loc[idx, "li"], d.loc[idx, "ls"] = li, ls
    return d


def metricas(bt: pd.DataFrame) -> pd.DataFrame:
    """Errores por modelo, por hora y por día. MASE < 1 = mejor que la línea base naive.
    Cobertura con intervalos calibrados fuera de muestra (misma regla para todos los modelos)."""
    if bt.empty:
        return pd.DataFrame()
    if "li" not in bt or bt["li"].isna().all():
        bt = calibrar(bt)
    dd = diario_calibrado(bt)
    out = []
    naive = bt[bt["modelo"] == "naive_semanal"]
    mae_naive_h = (naive["real"] - naive["pred"]).abs().mean()
    nd = dd[dd["modelo"] == "naive_semanal"]
    mae_naive_d = (nd["real"] - nd["pred"]).abs().mean()
    for m, g in bt.groupby("modelo", sort=False):
        e = g["real"] - g["pred"]
        d = dd[dd["modelo"] == m]
        ed = d["real"] - d["pred"]
        out.append({"modelo": m, "semanas": g["corte"].nunique(),
                    "mae_hora": e.abs().mean(), "rmse_hora": np.sqrt((e ** 2).mean()),
                    "sesgo_hora": e.mean(), "mase_hora": e.abs().mean() / mae_naive_h if mae_naive_h else np.nan,
                    "mae_dia": ed.abs().mean(), "mape_dia": (ed.abs() / d["real"].where(d["real"] > 0)).mean(),
                    "mase_dia": ed.abs().mean() / mae_naive_d if mae_naive_d else np.nan,
                    "media_real_hora": g["real"].mean(), "media_real_dia": d["real"].mean(),
                    "cobertura_intervalo": ((g["real"] >= g["li"]) & (g["real"] <= g["ls"])).mean(),
                    "cobertura_intervalo_dia": ((d["real"] >= d["li"]) & (d["real"] <= d["ls"])).mean(),
                    "alpha_hora": alpha_empirico(g["real"], g["pred"]),
                    "alpha_dia": alpha_empirico(d["real"], d["pred"])})
    return pd.DataFrame(out)


MODELOS_FINALES = ["glm", "glm_nivel"]   # los que pueden pronosticar el futuro con calendario


def elegir_modelo(met: pd.DataFrame) -> str:
    """El modelo con menor error diario en el backtest entre los que usan calendario (los festivos
    del horizonte importan). Las líneas base quedan como referencia."""
    m = met[met["modelo"].isin(MODELOS_FINALES)]
    return str(m.loc[m["mae_dia"].idxmin(), "modelo"]) if len(m) else "glm"


# --- interpretación ------------------------------------------------------------------------
def efectos(g: Glm) -> pd.DataFrame:
    """Efectos multiplicativos del calendario y la tendencia: exp(coef). 1.10 = 10 % más llegadas."""
    filas = []
    for col in CALENDARIO:
        k = f"cal_{col}"
        if k in g.coef:
            # Para festivo se promedia el efecto sobre las 24 horas
            if col == "festivo":
                extra = np.mean([g.coef.get(f"festivo_h{h:02d}", 0.0) for h in range(24)])
                filas.append({"efecto": col, "multiplicador": float(np.exp(g.coef[k] + extra))})
            else:
                filas.append({"efecto": col, "multiplicador": float(np.exp(g.coef[k]))})
    if "tendencia_anios" in g.coef:
        filas.append({"efecto": "tendencia_por_anio", "multiplicador": float(np.exp(g.coef["tendencia_anios"]))})
    return pd.DataFrame(filas)


def perfil_semana(g: Glm) -> pd.DataFrame:
    """Llegadas esperadas por hora de la semana en un día normal (sin festivo), relativas al
    promedio semanal: 1.5 = esa hora recibe 50 % más que la hora promedio."""
    b = np.array([g.coef.get(f"how_{k:03d}", 0.0) for k in range(H_SEMANA)])
    rel = np.exp(b - np.log(np.mean(np.exp(b))))
    return pd.DataFrame({"dia_semana": np.arange(H_SEMANA) // 24, "hora_dia": np.arange(H_SEMANA) % 24,
                         "relativo": rel})


# --- pronóstico futuro -------------------------------------------------------------------
def pronosticar(y: pd.Series, cal: pd.DataFrame, horas_futuras: pd.DatetimeIndex,
                modelo: str = "glm_nivel", alpha_hora: float | None = None) -> tuple[pd.DataFrame, Glm, float]:
    """Ajusta con toda la historia válida y pronostica `horas_futuras`. `glm_nivel` reescala al
    nivel de las últimas 4 semanas. Intervalo con la dispersión del backtest (`alpha_hora`) si se da;
    si no, con la del ajuste. Devuelve (pronóstico, glm, factor de nivel)."""
    g = ajustar_glm(y, cal)
    mu = g.media(horas_futuras, cal)
    factor = 1.0
    if modelo == "glm_nivel":
        factor = nivel_reciente(y, g, cal, y.dropna().index.max() + pd.Timedelta(hours=1))
        mu = mu * factor
    li, ls = intervalo_nb(mu, g.alpha_nb if alpha_hora is None else alpha_hora)
    return pd.DataFrame({"hora": horas_futuras, "pred": mu, "li": li, "ls": ls}), g, factor


def a_diario(df: pd.DataFrame, cols=("real", "pred")) -> pd.DataFrame:
    """Suma por día. El intervalo diario no es la suma de los horarios: se omite aquí y se
    calcula aparte con `intervalo_diario`."""
    cols = [c for c in cols if c in df]
    claves = [c for c in ("serie", "modelo", "corte", "tipo") if c in df]
    return (df.assign(fecha=df["hora"].dt.normalize())
              .groupby(claves + ["fecha"], dropna=False)[cols].sum(min_count=1).reset_index())


def intervalo_diario(mu_dia: np.ndarray, g: Glm | float, horas_por_dia: int = 24,
                     nivel: float = NIVEL_INTERVALO) -> tuple[np.ndarray, np.ndarray]:
    """Intervalo de la suma diaria. Suma de Poisson = Poisson; para la binomial negativa se usa
    una NB con la misma media y la varianza de la suma de las horas (aprox. horas independientes)."""
    a = (1 - nivel) / 2
    alpha = g.alpha_nb if isinstance(g, Glm) else float(g)
    mu_dia = np.asarray(mu_dia, dtype=float)
    if alpha > 1e-6:
        var = mu_dia + alpha * mu_dia ** 2 / horas_por_dia
        n = mu_dia ** 2 / np.maximum(var - mu_dia, 1e-9)
        p = n / (n + mu_dia)
        return stats.nbinom.ppf(a, n, p), stats.nbinom.ppf(1 - a, n, p)
    return stats.poisson.ppf(a, mu_dia), stats.poisson.ppf(1 - a, mu_dia)
