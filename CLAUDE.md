# CLAUDE.md — Data Challenge HUN 2026 · equipo The Outliers

Contexto para cualquier sesión de Claude (Claude Code o chat) que trabaje en este repo. Léelo completo antes de hacer nada.

Equipo: Diego, Sebastián y Joseph (Uninorte, Ciencia de Datos). Comunicación en español, casual y directa, sin preámbulos ni disclaimers innecesarios. Explica el porqué de las cosas, no solo el resultado.

---

## 0. Reglas de confidencialidad (no negociables)

Trabajamos con datos reales de pacientes del Hospital Universidad del Norte (HUN) bajo un acuerdo de confidencialidad. **Subir datos del HUN a una IA, a la nube o a terceros es causal de descalificación.** Por eso:

- **NO leas, abras, busques ni imprimas**: `.env`, la carpeta de datos (`DATA_DIR`, normalmente `C:\hun_data`), archivos `.parquet/.csv/.xlsx/.pbix`, ni la carpeta de DBeaver en AppData. `.claude/settings.json` lo bloquea, pero no dependas solo de eso.
- **NO ejecutes nada que se conecte a la base o cargue extractos**: `python -m hun.extract`, `python -m Cuellos_botella`, `python -m series_tiempo`, los `resumen_seguro` (de `scripts/` y de cada herramienta), `hun.db.ping`, notebooks con datos. Eso lo corre la persona; tú escribes el código. `.claude/settings.json` bloquea esos comandos; `pytest` sí se puede correr (usa datos inventados o la base sintética local).
- **Lo único que puedes recibir del usuario**: el esquema (tablas, columnas, tipos), nombres e IDs de conceptos OMOP, mensajes de error (revisando que no traigan valores) y la salida de los scripts `scripts/resumen_seguro*.py`, que traducen resultados a palabras ("pocos", "la mayoría") y franjas ("1-4 h"). **Nunca pidas conteos, filas, fechas de pacientes ni textos libres**, y si el usuario los pega, avísale y no los repitas.
- Nunca escribas cifras de los datos en archivos del repo (ni en docs, comentarios o commits). Los hallazgos van en palabras.
- Credenciales: solo en `.env` (ignorado por git). Nunca en código, notebooks, chats ni commits.
- Para probar código usa **datos sintéticos** (`scripts/generar_sintetico.py` en un PostgreSQL local), nunca la base real.
- Si algo parece una fuga (datos o credenciales en un archivo, en la terminal o en git), detente y avisa. Una exposición accidental se reporta a los organizadores.

## 1. El reto

- Problema: urgencias del HUN congestionada. Quieren trazabilidad del paciente, entender dónde se acumula la espera y **recomendaciones concretas para reducir tiempos**.
- Entrega: **20 nov 2026** (documento + repo GitHub sin datos + dashboard Power BI + presentación). Sustentación: 30 nov.
- Evaluación: optimización y propuestas de mejora 20 % · modelo analítico/predictivo 20 % · comprensión del problema y flujo 15 % · calidad y preparación de datos 15 % · dashboard 15 % · presentación 10 % · ingeniería de software/reproducibilidad 5 %. Desempate: optimización, luego modelo.
- Los jurados no tienen acceso a la base: el repo debe poder ejecutarse con los datos sintéticos.

## 2. Entorno

- Windows + PowerShell + VS Code. Python 3.11 en `.venv` (`.venv\Scripts\activate`).
- Base: PostgreSQL 18 del HUN, esquema `uninorte_omop`, accesible solo con la VPN del HUN (FortiClient; usuario de VPN compartido por el equipo, usuario de BD individual por persona).
- `.env` (copiado de `.env.example`): `PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD, PGSCHEMA, DATA_DIR`. `DATA_DIR` debe estar fuera del repo y fuera de OneDrive; `src/hun/config.py` se niega a correr si no.
- Setup de cada clon: `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1` (activa el hook anti-fuga y crea `.env`), luego `pip install -r requirements.txt` y `pip install -e .`.

## 3. Estructura del repo

```
.githooks/pre-commit        hook anti-fuga (llama a scripts/check_no_data.py --staged)
.github/workflows/          misma revisión en GitHub Actions
.claude/settings.json       reglas deny para Claude Code (.env, datos, --no-verify, --force)
docs/                       PROTOCOLO_DATOS.md, METODOLOGIA_EPISODIOS.md
sql/00_exploracion/         consultas de exploración (00-02, 07-18) y su README con lo que mostró cada una
sql/01_episodios/           _episodios.sql (bloque común) + consultas 20-25
sql/02_cuellos_botella/     entrada.sql (nivel paciente, @nivel_paciente: solo se lee a memoria)
Cuellos_botella/            herramienta exploratoria de Joseph (reporte HTML + tablas agregadas), ver su README
series_tiempo/              reporte y series para el pronóstico (consultas 26-28), ver su README
pronostico/                 modelo de pronóstico de llegadas por hora (GLM + backtest) y CSV para Power BI, ver su README
tests/                      tests de scripts/check_no_data.py (conftest.py en la raíz: rutas y base sintética)
src/hun/                    config.py (.env, DATA_DIR y validar_carpeta), db.py (conexión), extract.py, palabras.py
scripts/                    check_no_data.py, setup.*, resumen_seguro*.py, generar_sintetico.py
notebooks/                  análisis, SIEMPRE sin outputs
dashboard/                  Power BI como .pbit o PBIP, nunca .pbix
```

- `python -m hun.extract sql\...\archivo.sql` corre una consulta y guarda el resultado en `DATA_DIR/<nombre>.parquet`; en consola solo imprime filas y columnas. `hun.extract.load("<nombre>")` lo carga.
- `extract.py` envuelve la consulta en `sqlalchemy.text()` (los `%` de `ILIKE` no rompen psycopg2) y soporta `-- @include archivo.sql` para reutilizar bloques. Las consultas con `@include` no corren tal cual en DBeaver: hay que pegar el bloque incluido.
- Patrón para compartir resultados con Claude: por cada lote de consultas hay un `scripts/resumen_seguro_N.py` que lee los extractos y los imprime en palabras/franjas. Al crear consultas nuevas, crea también su resumen seguro, usando las funciones de `hun.palabras` (`cuanto`, `franja`, `veces`, `es`, `extracto`) para que todas las herramientas hablen igual.
- Consultas que devuelven una fila por paciente o segmento llevan la línea `-- @nivel_paciente`; `hun.extract` se niega a guardarlas. Se leen a memoria, p. ej. `python -m Cuellos_botella --config Cuellos_botella/config.yaml --entrada sql/02_cuellos_botella/entrada.sql`, y lo que queda en disco son tablas agregadas. Su resumen seguro: `python -m Cuellos_botella.resumen_seguro`.
- `Cuellos_botella/config.yaml` reproduce `_episodios.sql` y la consulta 25 (solo 9203/3045729/9201, urgencias = 9203 + 3045729, recorte al ingreso, sin urgencias > 7 días ni hospitalización > 90). `Cuellos_botella/tests/test_equivalencia_sql.py` lo comprueba contra la base sintética. **Si el equipo cambia una definición, hay que cambiarla en el SQL y en el config.**
- Los reportes generados llevan la marca `hun-datos` y el hook los bloquea; `muestra_carriles > 0` (episodios individuales) está bloqueado salvo `--permitir-carriles`.
- `python -m series_tiempo` corre las consultas agregadas 26-28 (26 = rejilla horaria completa de llegadas, ingresos, altas y censos como la 25; 27 = llegadas diarias por sexo, edad y destino; 28 = tiempos semanales con y sin recorte, solo grupos de 10+), agrega el calendario colombiano y deja en `DATA_DIR/series_tiempo` el reporte `reporte_series.html` y las series en parquet (`series_tiempo.cargar()`). Su resumen seguro: `python -m series_tiempo.resumen_seguro`. Son gráficas exploratorias: el modelado lo hace Sebastián.
- `python -m pronostico` lee las series de `series_tiempo` (no se conecta a la base), compara una línea base (misma hora de la semana pasada, promedio de 4 semanas) contra un GLM de conteos (hora de la semana, festivo × hora, calendario colombiano, tendencia; estacionalidad anual solo con 2+ años) con backtest rodante semanal, y deja en `DATA_DIR/pronostico/powerbi` los CSV para el dashboard (pronóstico horario y diario con intervalo del 90 %, backtest, métricas, efectos de calendario, perfil semanal). Su resumen seguro: `python -m pronostico.resumen_seguro`. Claude Code no lo corre (reglas deny).
- La 21 solo trae las horas con llegadas (hay que rellenar con 0); para series usa la 26.
- `main.py` (o doble clic en `ejecutar.bat`) es el menú para el equipo: revisa `.env` y VPN sin imprimir valores, corre series y/o cuellos de botella, abre el reporte y muestra el resumen seguro. Se conecta a la base: Claude Code no lo corre (está en las reglas deny).

## 4. Esquema real (7 tablas; no hay death, drug_exposure, observation, provider, etc.)

- `concept(concept_id, concept_name, domain_id, vocabulary_id)` — trae el vocabulario OMOP completo (que un concepto exista aquí no significa que se use).
- `person(person_id, gender_concept_id, year_of_birth, race_concept_id, ethnicity_concept_id)`
- `visit_occurrence(visit_occurrence_id, person_id, visit_concept_id, visit_start_datetime, visit_end_datetime, provider_id)`
- `visit_detail(visit_detail_id, visit_occurrence_id, visit_detail_concept_id, visit_detail_start_datetime, visit_detail_end_datetime, provider_id)` — sin person_id; se une por visit_occurrence_id.
- `condition_occurrence(..., condition_concept_id, condition_start_datetime, condition_type_concept_id)`
- `procedure_occurrence(..., procedure_concept_id, procedure_date)` — **solo fecha, sin hora**.
- `measurement(..., measurement_concept_id, measurement_datetime, value_as_number, measurement_source_value_extended)` — casi todo laboratorio (hemograma, electrolitos, creatinina, coagulación, gases, PCR, lactato). El texto libre puede ser sensible: nunca compartir valores.

## 5. Cómo registra el HUN el flujo (confirmado con datos, en palabras)

Conceptos usados en `visit_occurrence` y `visit_detail`:

```
Llegada/registro            Atención en urgencias            Hospitalización
9203 Emergency Room Visit → 3045729 Treatment urgency    →   9201 Inpatient Visit
dura 0 o <15 min            típico 1-4 h, cola larga         típico 1-7 días
(marca, no estancia)        (varios segmentos seguidos)
```

- **3045729 "Treatment urgency"** en OMOP estándar es un concepto de observación, pero el HUN lo usa como tipo de visita/segmento: es la **estancia real en urgencias**. Filtrar urgencias solo por 9203 pierde casi toda la atención.
- **581479 "Ambulatory Rehabilitation Visit"**: siempre dura 0; eventos ambulatorios puntuales (probable consulta externa), fuera del flujo de urgencias.
- `visit_occurrence` casi siempre tiene inicio = fin → **no sirve para duraciones**. Las duraciones salen de `visit_detail`.
- **Una visit_occurrence NO es un episodio**: agrupa segmentos separados por días. Hay que reconstruir episodios.
- Las horas son reales (casi ninguna en 00:00) → el análisis por hora es viable.
- **No existe nivel de triaje (I-V)** ni etapas internas (triaje/admisión/consulta). "Triage level" está en el vocabulario pero no se usa. Es una limitación a declarar.

## 6. Episodios (`sql/01_episodios/_episodios.sql`, ver `docs/METODOLOGIA_EPISODIOS.md`)

- Por paciente, se unen segmentos 9203/3045729/9201 solapados o con hueco ≤ 60 min (gaps and islands). `ep` = todos los episodios; `epu` = los que empiezan en urgencias, con `destino` (alta/hospitalizado), `min_urg`, `min_hosp`.
- Resultados en palabras:
  - Casi todos los episodios de urgencias terminan en alta; se hospitalizan pocos.
  - **Hallazgo principal: los hospitalizados pasan más de 3 veces más tiempo en urgencias que los de alta** (la espera de cama queda dentro del tiempo en urgencias). Es la pista para las recomendaciones: el cuello de botella parece ser el acceso a cama, no la atención.
  - ⚠️ **Por verificar:** ese "más de 3 veces" sale de `min_urg` de la 20, que NO recorta urgencias al ingreso a cama. Como en bastantes hospitalizados el registro de urgencias sigue abierto después del ingreso (ver diagnóstico de ocupación), parte de ese tiempo es tiempo en cama. Hay que repetir la comparación con recorte (Cuellos_botella con `recortar_al_siguiente: true`: tabla `comparativa_recorte` y `rel_destino`) antes de usar la cifra en el documento.
  - Episodios de alta: distribución bimodal; la mayoría dura menos de 15 min (¿registro/remisión de triaje IV-V a EPS? por confirmar).
  - Serie de llegadas por hora: continua, sin días vacíos, patrón diario fuerte (hora pico > 3 veces la más tranquila), semanal moderado. **Los últimos meses disponibles (2026) están incompletos: excluirlos de modelos.**
  - El tiempo en urgencias varía 1.5-3 veces según la hora de llegada.
- Diagnóstico de ocupación (consultas 23-25):
  - La ocupación calculada supera muchas veces la capacidad de referencia (58 cubículos de urgencias, 64 camas, tomadas de la visita de campo). Censo estable entre años (sin deriva).
  - Causas encontradas: en bastantes hospitalizados el registro de urgencias sigue abierto días después del ingreso (doble conteo; 25 lo corrige cortando urgencias al ingreso); pocos episodios de más de 7 días aportan muchas horas-paciente.
  - Aun ajustada, hospitalización sigue muy por encima de 64 camas → la capacidad de referencia no cubre todo lo que hay en los datos. **La ocupación absoluta NO es confiable todavía; los patrones relativos sí.**
  - Cuando una hospitalización llega después de una urgencia con hueco (< 48 h), el hueco típico es de 12-24 h → posible espera de cama no registrada; el umbral de 60 min separa flujos reales.

## 7. Decisiones abiertas (las toma el equipo, no Claude)

1. Umbral de episodio: ¿unir urgencia → hospitalización aunque haya horas de hueco (24-48 h)?
2. Tratamiento de contactos < 15 min y de la cola larga (> 7 días).
3. Capacidades reales a usar.
3b. Episodios irregulares (urgencias reaparece después de la hospitalización): ¿registro abierto, traslado de vuelta a urgencias o error? Hoy el SQL y la herramienta los miden distinto (ver README de Cuellos_botella). El resumen seguro dice cuántos hay.
4. Reparto del trabajo: pronóstico (llegadas/ocupación por hora), simulación de escenarios (p. ej. agilizar ingreso a cama, reforzar franjas pico), dashboard Power BI, documento y presentación.

Preguntas enviadas/por enviar a los organizadores: acceso por VPN desde equipos propios, descarga de extractos, OneDrive institucional, Power BI directo a la BD, uso simultáneo de la VPN, uso de IA con agregados, significado de 9203/3045729/581479 y si existe triaje, capacidad real y sedes cubiertas, qué son los contactos < 15 min. **Mientras no respondan: trabajar con agregados, sin descargar datos por paciente.**

## 8. Contexto de la visita de campo (1 oct)

- Por ley se atienden triaje I, II y III (Res. 5596/2015); IV y V se remiten a la EPS.
- Flujo observado: turno → triaje → sala de espera → admisiones (verifican EPS) → consultorio → alta u observación → hospitalización/UCI/cirugía/exámenes. En congestión se habilitan consultorios y se atiende en silla.
- Hay demoras "naturales" (labs remitidos fuera) que no son ineficiencia.
- Capacidad mencionada: 58 cubículos de urgencias, 4 de reanimación, 3 quirófanos, 64 camas de hospitalización (pisos 1 y 2). Tres sedes.
- Análisis sugeridos por el HUN: Sankey de trayectorias, cascada de esperas, boxplots de estancia por servicio, heatmap día × hora, series de tiempo por hora/día.

## 9. Forma de trabajar

- Claude escribe SQL/código y lo prueba con datos sintéticos; la persona lo corre contra la base real y comparte solo el resumen seguro.
- Claude (chat) puede trabajar en una rama `claude/...` del repo y abrir un pull request; **nunca toca `main`**. La persona revisa el PR (en GitHub o con su Claude Code) y decide si lo fusiona. Nadie fusiona una rama `claude/...` sin revisarla.
- GitHub Actions corre el chequeo anti-fuga y todos los tests con la base sintética en cada push y PR.
- Commits: la persona decide. Claude Code agrega archivos uno por uno (nunca `git add -A`), corre `python scripts/check_no_data.py --all`, muestra un resumen y **espera confirmación antes del push**. Nunca `--no-verify` ni `--force`.
- Notebooks sin outputs (`nbstripout --install` o `jupyter nbconvert --clear-output --inplace`).
- Power BI: nunca subir `.pbix` (lleva los datos); usar `.pbit` o PBIP sin caché.
