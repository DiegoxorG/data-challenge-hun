# Data Challenge HUN 2026 — The Outliers

Análisis del flujo de urgencias del Hospital Universidad del Norte (HUN) sobre su base OMOP CDM en PostgreSQL:

- reconstrucción de episodios y trayectorias de pacientes;
- dónde y cuándo se acumula la espera (cuellos de botella);
- **pronóstico** de llegadas por hora a 14 días, evaluado con backtest;
- **escenarios** de mejora cuantificados con la ley de Little;
- un **semáforo de saturación por turno** (alerta temprana) con protocolo de acción;
- propuestas de mejora operacional y un dashboard en Power BI.

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
| `python -m pronostico --excluir-ultimas-semanas 6` | Pronóstico de llegadas por hora (14 días) con intervalo del 90 %: GLM de conteos frente a líneas base, backtest rodante e intervalos calibrados fuera de muestra. [README](pronostico/README.md) | `pronostico/` |
| `python -m escenarios` | Cuánto baja la congestión de urgencias si se reduce la espera de cama o se adelantan altas (ley de Little, hora por hora) | `escenarios/` |
| `python -m semaforo` | Semáforo verde/amarillo/rojo por turno para los próximos 14 días, con protocolo de acción y validación contra la referencia. [README](semaforo/README.md) | `semaforo/` |
| `python -m pronostico.reporte` | Reporte local para interpretar pronóstico, escenarios y semáforo (lleva datos: no se comparte) | `reporte_interpretacion.html` |
| `python scripts/resumen_seguro_perfiles.py` | Perfiles de pacientes (sexo y edad) en palabras, a partir de las tablas de Cuellos_botella | en pantalla |

`pronostico`, `escenarios` y `semaforo` **no se conectan a la base**: leen las series agregadas que deja `series_tiempo` y escriben CSV listos para Power BI en `DATA_DIR/<módulo>/powerbi`. La opción `--excluir-ultimas-semanas 6` es necesaria con los datos del HUN: las semanas previas a los meses incompletos tienen registro rezagado (ver `pronostico/README.md`).

Cada herramienta tiene un `resumen_seguro` que traduce los resultados a palabras: es lo único que se comparte con Claude.

```bash
python -m pronostico.resumen_seguro
python -m escenarios.resumen_seguro
python -m semaforo.resumen_seguro
```

## Reproducir sin acceso a la base del HUN (jurados)

El repositorio corre de punta a punta sobre una **base sintética**: datos inventados con la misma estructura OMOP y patrones parecidos (perfil horario, lunes más cargados, estacionalidad suave). Con ella los resultados **no** coinciden con los del informe; sirve para verificar que el código funciona.

**Requisitos:** Python 3.11+ y un PostgreSQL **local** (el generador se niega a escribir en un servidor que no sea `localhost`).

```bash
# 1. Entorno
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# 2. Base sintética en un PostgreSQL local (crea la base vacía antes, p. ej. con createdb omop_sintetico)
python scripts/generar_sintetico.py --url postgresql://yo@localhost:5432/omop_sintetico --pacientes 20000

# 3. .env apuntando a la base sintética (copia .env.example) y una DATA_DIR aparte, fuera del repo:
#    PGHOST=localhost  PGPORT=5432  PGDATABASE=omop_sintetico  PGUSER=yo, y tu clave local en la variable de clave
#    PGSCHEMA=uninorte_omop  DATA_DIR=C:\sintetico_data   (o /tmp/sintetico_data)

# 4. Pipeline completo
python -m Cuellos_botella --config Cuellos_botella/config.yaml --entrada sql/02_cuellos_botella/entrada.sql
python -m series_tiempo
python -m pronostico --excluir-ultimas-semanas 6
python -m escenarios
python -m semaforo
python -m pronostico.reporte          # abre el reporte de interpretación
python scripts/resumen_seguro_perfiles.py

# 5. Tests (los de pronostico, escenarios y semaforo usan datos generados dentro del test;
#    los que necesitan base usan la sintética)
HUN_TEST_PG_URL=postgresql://yo@localhost:5432/omop_sintetico python -m pytest
```

GitHub Actions hace exactamente esto en cada push (`.github/workflows/check-no-data.yml`): revisa que no haya datos, crea la base sintética, corre los tests y el pipeline completo.

## Estructura

```
.githooks/pre-commit        bloquea datos y credenciales antes del commit
.github/workflows/          misma revisión en GitHub (segunda barrera)
docs/                       protocolo de datos, metodología, decisiones
sql/                        consultas (versionadas); los resultados NO
src/hun/                    config (.env + DATA_DIR validada), conexión, extracción, palabras de los resúmenes
Cuellos_botella/            reporte de cuellos de botella (Joseph)
series_tiempo/              reporte y series para el pronóstico
pronostico/                 modelo de pronóstico (GLM + backtest), reporte de interpretación
escenarios/                 escenarios de mejora (ley de Little)
semaforo/                   semáforo de saturación por turno (alerta temprana)
notebooks/                  guía de familiarización y análisis, siempre sin outputs
dashboard/                  Power BI como .pbit o PBIP, nunca .pbix
scripts/                    setup, verificador anti-fuga, generador sintético, resúmenes seguros
tests/                      tests del verificador anti-fuga y de los resúmenes seguros
```

## Equipo

The Outliers — Joseph Arias, Sebastian Ariza y Diego Payares. Universidad del Norte, Data Challenge HUN 2026.
