"""Carga y valida config.yaml. Nada específico de un dataset vive en el código:
columnas, umbrales, zonas a excluir y capacidades salen de aquí."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CARPETA_SALIDA_DEFECTO = "cuellos_botella_salidas"

# Mismo criterio que src/hun/config.py: nada de carpetas sincronizadas a la nube
_SYNCED = ("onedrive", "google drive", "googledrive", "my drive", "mi unidad",
           "icloud", "dropbox", "mobile documents", "box sync", "mega")


@dataclass
class Atributo:
    columna: str
    tipo: str = "categorica"          # categorica | numerica
    bins: list[float] | None = None   # solo numéricas; None = quintiles


@dataclass
class Grupo:
    """Varias zonas de la entrada que se analizan como una sola (p. ej. llegada + atención = urgencias)."""
    codigos: list[str]
    etiqueta: str


@dataclass
class Config:
    persona: str
    zona: str
    inicio: str
    fin: str
    etiqueta_zona: str | None = None
    caso: str | None = None
    atributos: list[Atributo] = field(default_factory=list)
    edad_desde_anio_nacimiento: str | None = None
    umbral_min: float = 60.0
    recortar_al_siguiente: bool = False
    zonas_incluir: list[str] = field(default_factory=list)       # vacío = todas las zonas
    zonas_excluir: list[str] = field(default_factory=list)
    zonas_agrupar: dict[str, Grupo] = field(default_factory=dict)  # código final -> grupo
    excluir_estancias_largas: dict[str, float] = field(default_factory=dict)  # zona final -> días
    capacidades: dict[str, float] = field(default_factory=dict)
    desde: str | None = None
    hasta: str | None = None
    ventana_carga_h: float = 3.0
    top_n_categorias: int = 8
    tamano_min_grupo: int = 30
    cuantiles_censo: int = 5
    mes_incompleto_frac: float = 0.5
    mes_cobertura_min: float = 0.9
    ventana_reconsulta_h: float = 48.0
    pasos_sankey: int = 4
    max_zonas_solape: int = 40
    minutos_bin_perfil: int = 60      # granularidad de los perfiles del día: 60, 30 o 15
    muestra_carriles: int = 0         # 0 = no dibujar el diagrama de carriles

    @property
    def columnas_entrada(self) -> list[str]:
        cols = [self.persona, self.zona, self.inicio, self.fin, self.etiqueta_zona, self.caso,
                self.edad_desde_anio_nacimiento]
        cols += [a.columna for a in self.atributos if a.columna != "edad" or not self.edad_desde_anio_nacimiento]
        vistos: list[str] = []
        for c in cols:
            if c and c not in vistos:
                vistos.append(c)
        return vistos


def _texto(v) -> str | None:
    return None if v in (None, "") else str(v)


def _grupos(raw: dict) -> dict[str, Grupo]:
    """{grupo: {codigos: [...], etiqueta: "..."}} -> {grupo: Grupo}; un código no puede estar en dos grupos."""
    out: dict[str, Grupo] = {}
    vistos: dict[str, str] = {}
    for nombre, g in raw.items():
        if not isinstance(g, dict) or not g.get("codigos"):
            raise ValueError(f"config: el grupo {nombre!r} de zonas_agrupar necesita una lista 'codigos'")
        codigos = [str(c) for c in g["codigos"]]
        for c in codigos:
            if c in vistos:
                raise ValueError(f"config: la zona {c!r} está en dos grupos ({vistos[c]!r} y {nombre!r})")
            vistos[c] = str(nombre)
        out[str(nombre)] = Grupo(codigos=codigos, etiqueta=str(g.get("etiqueta") or nombre))
    return out


def cargar(ruta: str | Path) -> Config:
    with open(ruta, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    col = raw.get("columnas") or {}
    faltan = [k for k in ("persona", "zona", "inicio", "fin") if not col.get(k)]
    if faltan:
        raise ValueError(f"config: faltan columnas obligatorias en 'columnas': {faltan}")

    atributos = []
    for a in col.get("atributos") or []:
        if isinstance(a, str):
            a = {"columna": a}
        tipo = a.get("tipo", "categorica")
        if tipo not in ("categorica", "numerica"):
            raise ValueError(f"config: tipo de atributo inválido {tipo!r} (usa categorica o numerica)")
        atributos.append(Atributo(columna=str(a["columna"]), tipo=tipo, bins=a.get("bins")))

    ep = raw.get("episodios") or {}
    fechas = raw.get("rango_fechas") or {}
    par = raw.get("parametros") or {}

    cfg = Config(
        persona=str(col["persona"]), zona=str(col["zona"]),
        inicio=str(col["inicio"]), fin=str(col["fin"]),
        etiqueta_zona=_texto(col.get("etiqueta_zona")), caso=_texto(col.get("caso")),
        atributos=atributos,
        edad_desde_anio_nacimiento=_texto(raw.get("edad_desde_anio_nacimiento")),
        umbral_min=float(ep.get("umbral_min", 60)),
        recortar_al_siguiente=bool(ep.get("recortar_al_siguiente", False)),
        zonas_incluir=[str(z) for z in raw.get("zonas_incluir") or []],
        zonas_excluir=[str(z) for z in raw.get("zonas_excluir") or []],
        zonas_agrupar=_grupos(raw.get("zonas_agrupar") or {}),
        excluir_estancias_largas={str(k): float(v) for k, v in (raw.get("excluir_estancias_largas") or {}).items()},
        capacidades={str(k): float(v) for k, v in (raw.get("capacidades") or {}).items()},
        desde=_texto(fechas.get("desde")), hasta=_texto(fechas.get("hasta")),
    )
    for k, v in par.items():
        if not hasattr(cfg, k):
            raise ValueError(f"config: parámetro desconocido {k!r}")
        setattr(cfg, k, type(getattr(cfg, k))(v))
    if cfg.minutos_bin_perfil not in (15, 30, 60):
        raise ValueError("config: minutos_bin_perfil debe ser 15, 30 o 60")
    return cfg


def validar_salida(ruta: str | Path | None) -> Path:
    """Devuelve la carpeta de salida. Por defecto DATA_DIR/cuellos_botella_salidas;
    nunca dentro del repo ni en una carpeta sincronizada a la nube."""
    if ruta is None:
        try:
            from hun.config import data_dir  # lee DATA_DIR del .env del usuario
        except Exception as e:  # pragma: no cover - depende del entorno
            raise RuntimeError("No pude obtener DATA_DIR (¿instalaste el paquete hun y llenaste .env?). "
                               "Indica la salida con --salida.") from e
        d = data_dir() / CARPETA_SALIDA_DEFECTO
    else:
        d = Path(ruta).expanduser().resolve()
    if d == REPO_ROOT or REPO_ROOT in d.parents:
        raise RuntimeError(f"La salida ({d}) está DENTRO del repo. Usa una carpeta fuera, p. ej. DATA_DIR.")
    if any(s in str(d).lower() for s in _SYNCED):
        raise RuntimeError(f"La salida ({d}) parece estar en una carpeta sincronizada a la nube.")
    d.mkdir(parents=True, exist_ok=True)
    return d
