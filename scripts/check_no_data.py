#!/usr/bin/env python3
"""
Guardián anti-fuga de datos del HUN.

Revisa archivos y bloquea:
  1. Extensiones / carpetas de datos (csv, parquet, pbix, xlsx, data/, ...)
  2. Archivos de más de MAX_MB megas
  3. Notebooks (.ipynb) con outputs guardados o imágenes pegadas (muestran datos)
  4. Credenciales en el contenido (URIs de Postgres con clave, password=..., PGPASSWORD)
  5. Texto que parece una tabla pegada (muchas filas delimitadas), también en celdas de notebooks
  6. Reportes generados con datos (marca hun-datos)
  7. Archivos que no se pueden leer (no se dejan pasar sin revisar)

Uso:
  python scripts/check_no_data.py --staged   # lo que vas a commitear (hook pre-commit)
  python scripts/check_no_data.py --all      # todo lo versionado (CI en GitHub)

Sale con código 1 si encuentra algo. Solo usa la librería estándar.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import PurePosixPath

# La consola de Windows (cp1252) no imprime "✔"/"✘" y el script se caería con código 1,
# bloqueando commits limpios. Forzamos UTF-8 en la salida.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

MAX_MB = 2
DELIMITED_ROWS_LIMIT = 40  # filas "tipo tabla" tolerables en un archivo de texto

BLOCKED_EXT = {
    ".csv", ".tsv", ".parquet", ".feather", ".arrow", ".orc", ".avro",
    ".xlsx", ".xls", ".xlsm", ".ods", ".jsonl", ".ndjson",
    ".h5", ".hdf5", ".npy", ".npz", ".pkl", ".pickle", ".joblib",
    ".rds", ".rdata", ".rda", ".sav", ".dta", ".sas7bdat",
    ".db", ".sqlite", ".sqlite3", ".duckdb", ".dump", ".backup", ".bak", ".pgdump",
    ".zip", ".7z", ".rar", ".tar", ".tgz", ".gz",
    ".pbix", ".abf",
    ".pem", ".key", ".ovpn",
}
BLOCKED_DIRS = {"data", "datos", "raw", "extracts", "dumps", "exports", "output", "outputs", "secrets"}
BLOCKED_NAMES = {".env", ".pgpass", "credentials-config.json", "pgadmin4.db"}
ALLOWED_NAMES = {".env.example"}

CRED_PATTERNS = [
    (re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:[^@\s]+@", re.I), "URI de Postgres con contraseña"),
    (re.compile(r"""\b(?:password|passwd|pwd|pw|pass|contrase[nñ]a|clave)[ \t]*[:=][ \t]*["'][^"'\s]{3,}["']""", re.I),
     "contraseña escrita en el código"),
    (re.compile(r"PGPASSWORD[ \t]*=[ \t]*[^\s$<{]{3,}"), "PGPASSWORD con valor"),
]
# Valores de ejemplo que no cuentan como credencial real
PLACEHOLDERS = re.compile(r"(cambiar|change|xxx|\*\*\*|tu_|your_|<|\$\{|os\.environ|getenv)", re.I)

# Marca que llevan los reportes generados con datos (p. ej. Cuellos_botella/reporte.py)
MARCA_DERIVADO = re.compile(r"""<meta\s+name=["']hun-datos["']""", re.I)

DELIM_ROW = re.compile(r"^[^\n]*?(?:[,;\t|][^,;\t|\n]*){4,}$")
TEXT_EXT = {".py", ".sql", ".md", ".txt", ".r", ".rmd", ".qmd", ".json", ".yml", ".yaml",
            ".toml", ".ini", ".cfg", ".dax", ".m", ".tmdl", ".html", ".js", ".ts", ".ps1", ".psm1",
            ".sh", ".bat", ".cmd", ".xml", ".svg", ".css", ".example", ""}


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def list_files(mode: str) -> list[str]:
    if mode == "--staged":
        out = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    else:
        out = git("ls-files", "-z")
    return [p for p in out.decode("utf-8", "replace").split("\0") if p]


def read_file(path: str, mode: str) -> bytes:
    if mode == "--staged":
        return git("show", f":{path}")
    with open(path, "rb") as fh:
        return fh.read()


def check(path: str, data: bytes) -> list[str]:
    problems: list[str] = []
    p = PurePosixPath(path)
    name = p.name.lower()
    suffixes = [s.lower() for s in p.suffixes]

    if name in ALLOWED_NAMES:
        pass
    elif name in BLOCKED_NAMES or name.startswith(".env"):
        problems.append("archivo de credenciales/config local")
    if any(s in BLOCKED_EXT for s in suffixes):
        problems.append(f"extensión de datos/binario ({''.join(suffixes)})")
    if any(part.lower() in BLOCKED_DIRS for part in p.parts[:-1]):
        problems.append("está dentro de una carpeta de datos")
    if ".pbi" in p.parts and "cache" in name:
        problems.append("caché de Power BI (contiene los datos)")

    size_mb = len(data) / (1024 * 1024)
    if size_mb > MAX_MB:
        problems.append(f"pesa {size_mb:.1f} MB (límite {MAX_MB} MB)")

    nb_fuente = ""
    if p.suffix.lower() == ".ipynb":
        try:
            nb = json.loads(data.decode("utf-8"))
            celdas = nb.get("cells", [])
            dirty = sum(1 for c in celdas if c.get("outputs"))
            if dirty:
                problems.append(f"notebook con outputs guardados en {dirty} celda(s): "
                                "limpia con 'jupyter nbconvert --clear-output --inplace'")
            # Imágenes pegadas en celdas markdown (capturas de gráficas o tablas)
            adjuntos = sum(1 for c in celdas if c.get("attachments"))
            if adjuntos:
                problems.append(f"notebook con imágenes pegadas en {adjuntos} celda(s) markdown")
            nb_fuente = "\n".join("".join(c.get("source", [])) for c in celdas)
        except Exception:
            problems.append("notebook ilegible")

    if p.suffix.lower() in TEXT_EXT or p.suffix.lower() == ".ipynb":
        text = data.decode("utf-8", "replace")
        for rx, label in CRED_PATTERNS:
            for m in rx.finditer(text):
                if not PLACEHOLDERS.search(m.group(0)):
                    line = text.count("\n", 0, m.start()) + 1
                    problems.append(f"{label} (línea {line})")
        if MARCA_DERIVADO.search(text):
            problems.append("reporte generado a partir de datos del HUN (marca hun-datos)")
        # En notebooks se mira el código y el markdown de las celdas (no el JSON)
        cuerpo = nb_fuente if p.suffix.lower() == ".ipynb" else text
        rows = sum(1 for ln in cuerpo.splitlines() if DELIM_ROW.match(ln))
        if rows > DELIMITED_ROWS_LIMIT:
            problems.append(f"{rows} líneas con forma de tabla: ¿datos pegados?")
    return problems


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--staged"
    if mode not in {"--staged", "--all"}:
        print(__doc__)
        return 2
    found = {}
    for path in list_files(mode):
        try:
            data = read_file(path, mode)
        except FileNotFoundError:
            continue                     # --all: archivo versionado que se borró sin commitear
        except Exception as e:           # si no se puede revisar, no se deja pasar
            found[path] = [f"no pude leerlo para revisarlo ({type(e).__name__})"]
            continue
        probs = check(path, data)
        if probs:
            found[path] = probs

    if not found:
        print("✔ check_no_data: sin datos ni credenciales detectados.")
        return 0

    print("\n✘ BLOQUEADO — posible fuga de datos del HUN o credenciales:\n")
    for path, probs in found.items():
        print(f"  {path}")
        for pr in probs:
            print(f"     - {pr}")
    print("\nQué hacer:")
    print("  git restore --staged <archivo>   (sacarlo del commit)")
    print("  y mover los datos a tu DATA_DIR, fuera del repo. Ver docs/PROTOCOLO_DATOS.md")
    print("  Si es un falso positivo, coméntalo con el equipo. NUNCA uses --no-verify.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
