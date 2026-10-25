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

1. Escribe la consulta en `sql/` (se versiona). Si devuelve una fila por paciente o segmento, márcala con `-- @nivel_paciente`.
2. Extrae a tu `DATA_DIR` (solo agregados): `python -m hun.extract sql/01_episodios/21_llegadas_por_hora.sql`
3. Analiza en `notebooks/` cargando con `hun.extract.load("21_llegadas_por_hora")`.
4. Antes de commitear un notebook, limpia los outputs (el hook te lo exige).
5. Commit → el hook revisa que no vaya nada sensible. GitHub Actions vuelve a revisar y corre los tests con la base sintética en cada push.

## Herramientas

**La forma fácil:** doble clic en `ejecutar.bat`, o abre `main.py` en VS Code y dale a ▶ (Run Python File). Sale un menú: revisa tu `.env` y la VPN, corre el reporte que elijas, lo abre en el navegador y muestra el resumen seguro. Lo mismo a mano:

| Comando | Para qué | Salida (en `DATA_DIR`) |
|---|---|---|
| `notebooks/00_guia_familiarizacion.ipynb` | Conocer la base con tus propios ojos | en pantalla |
| `python -m Cuellos_botella --config Cuellos_botella/config.yaml --entrada sql/02_cuellos_botella/entrada.sql` | Dónde se acumula la espera (flujo, censo, transiciones) | `cuellos_botella_salidas/` |
| `python -m series_tiempo` | Gráficas exploratorias de las series (EDA) para el pronóstico, y las series listas para modelar | `series_tiempo/` |

Cada herramienta tiene un `resumen_seguro` que traduce los resultados a palabras: es lo único que se comparte con Claude.

## Probar sin la base del HUN

```bash
# PostgreSQL LOCAL de pruebas (nunca el del HUN): crea una base inventada con la misma estructura
python scripts/generar_sintetico.py --url postgresql://yo@localhost:5432/omop_sintetico --pacientes 20000
HUN_TEST_PG_URL=postgresql://yo@localhost:5432/omop_sintetico python -m pytest
```

## Estructura

```
.githooks/pre-commit        bloquea datos y credenciales antes del commit
.github/workflows/          misma revisión en GitHub (segunda barrera)
docs/                       protocolo de datos, metodología, decisiones
sql/                        consultas (versionadas); los resultados NO
src/hun/                    config (.env + DATA_DIR validada), conexión, extracción, palabras de los resúmenes
Cuellos_botella/            reporte de cuellos de botella (Joseph)
series_tiempo/              reporte y series para el pronóstico
notebooks/                  guía de familiarización y análisis, siempre sin outputs
dashboard/                  Power BI como .pbit o PBIP, nunca .pbix
scripts/                    setup, verificador anti-fuga, generador sintético, resúmenes seguros
tests/                      tests del verificador anti-fuga
```

## Equipo

The Outliers — Universidad del Norte, Data Challenge 2026 (división HUN).
