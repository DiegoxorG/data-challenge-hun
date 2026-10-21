# Data Challenge HUN 2026 — The Outliers

Análisis del flujo de urgencias del Hospital Universidad del Norte (HUN) sobre su base OMOP CDM en PostgreSQL: tiempos por etapa, trayectorias de pacientes, congestión por franja horaria y pronóstico de ocupación, con propuestas de mejora operacional y un dashboard en Power BI.

> **Este repositorio no contiene ni debe contener datos del HUN.**
> Solo código, consultas SQL, documentación y resultados agregados. Los extractos viven en la carpeta `DATA_DIR` de cada integrante, fuera del repo. Antes de tu primer commit lee [`docs/PROTOCOLO_DATOS.md`](docs/PROTOCOLO_DATOS.md).

## Puesta en marcha (cada integrante, una vez)

```bash
git clone https://github.com/<usuario>/data-challenge-hun.git
cd data-challenge-hun

python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Activa los hooks anti-fuga y crea tu .env
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # Windows
sh scripts/setup.sh                                          # macOS/Linux
```

Luego llena `.env` con tus credenciales del HUN y una `DATA_DIR` local (p. ej. `C:\hun_data`), fuera del repo y fuera de OneDrive/Drive/iCloud. Prueba la conexión:

```bash
python -c "from hun.db import ping; ping()"
```

## Flujo de trabajo

1. Escribe la consulta en `sql/` (se versiona).
2. Extrae a tu `DATA_DIR`: `python -m hun.extract sql/00_exploracion/03_llegadas_heatmap.sql`
3. Analiza en `notebooks/` cargando con `hun.extract.load("03_llegadas_heatmap")`.
4. Antes de commitear un notebook, limpia los outputs (el hook te lo exige).
5. Commit → el hook revisa que no vaya nada sensible. GitHub Actions vuelve a revisar en cada push.

## Estructura

```
.githooks/pre-commit        bloquea datos y credenciales antes del commit
.github/workflows/          misma revisión en GitHub (segunda barrera)
docs/                       protocolo de datos, metodología, decisiones
sql/                        consultas (versionadas); los resultados NO
src/hun/                    config (.env + DATA_DIR validada), conexión, extracción
notebooks/                  análisis, siempre sin outputs
dashboard/                  Power BI como .pbit o PBIP, nunca .pbix
scripts/                    setup y verificador anti-fuga
```

## Equipo

The Outliers — Universidad del Norte, Data Challenge 2026 (división HUN).
