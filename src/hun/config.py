"""Configuración local: credenciales y carpeta de datos, siempre desde .env.

DATA_DIR tiene que estar FUERA del repo y fuera de carpetas sincronizadas
a la nube. Si no, el código se detiene antes de escribir un solo archivo.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

# Nombres de carpetas que suelen sincronizarse con la nube
_SYNCED = ("onedrive", "google drive", "googledrive", "my drive", "mi unidad",
           "icloud", "dropbox", "mobile documents", "box sync", "mega")


def _require(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(f"Falta {name} en tu .env (copia .env.example y llénalo).")
    return val


def data_dir() -> Path:
    """Carpeta local de extractos, validada contra fugas."""
    d = Path(_require("DATA_DIR")).expanduser().resolve()
    if d == REPO_ROOT or REPO_ROOT in d.parents:
        raise RuntimeError(f"DATA_DIR ({d}) está DENTRO del repo. Muévela fuera, p. ej. C:\\hun_data")
    if any(s in str(d).lower() for s in _SYNCED):
        raise RuntimeError(f"DATA_DIR ({d}) parece estar en una carpeta sincronizada a la nube. "
                           "Usa una carpeta local, p. ej. C:\\hun_data")
    d.mkdir(parents=True, exist_ok=True)
    return d


def pg_params() -> dict:
    return {
        "host": _require("PGHOST"),
        "port": int(os.getenv("PGPORT", "5432")),
        "dbname": _require("PGDATABASE"),
        "user": _require("PGUSER"),
        "password": _require("PGPASSWORD"),
    }


def schema() -> str:
    return os.getenv("PGSCHEMA", "uninorte_omop")
