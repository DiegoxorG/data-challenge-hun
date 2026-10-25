# Cuellos de botella: herramienta exploratoria

Genera gráficas, tablas y métricas a partir de un registro de eventos (persona, zona, inicio, fin) para **buscar dónde se acumula la espera**. No concluye: cada figura explica qué muestra y cómo leerla, y la interpretación queda en manos del equipo.

Es genérica: las zonas se descubren de los datos y todo lo específico (columnas, umbral de episodio, zonas incluidas y agrupadas, límites de estancia, capacidades, fechas) va en `config.yaml`. El `config.yaml` del repo reproduce las definiciones oficiales del equipo (`sql/01_episodios/_episodios.sql` y la consulta 25); `tests/test_equivalencia_sql.py` lo comprueba.

## Uso

```powershell
pip install -r requirements.txt

# Reporte completo leyendo DIRECTO de la base (VPN + .env). Los datos por paciente quedan
# solo en memoria; en disco quedan las tablas agregadas y el reporte.
# Sin --salida escribe en DATA_DIR\cuellos_botella_salidas
python -m Cuellos_botella --config Cuellos_botella/config.yaml --entrada sql/02_cuellos_botella/entrada.sql

# También acepta un CSV o Parquet (p. ej. datos sintéticos)
python -m Cuellos_botella --config Cuellos_botella/config.yaml --entrada <archivo.csv|parquet> [--salida <carpeta>]

# Lo único que se puede compartir con Claude: palabras y franjas, sin cifras
python -m Cuellos_botella.resumen_seguro [--salida <carpeta>]

# Tests (datos mínimos construidos dentro de cada test)
python -m pytest Cuellos_botella/tests

# Test de equivalencia con el SQL: necesita el PostgreSQL LOCAL sintético (scripts/generar_sintetico.py)
$env:HUN_TEST_PG_URL = "postgresql://yo@localhost:5432/omop_sintetico"
python -m pytest Cuellos_botella/tests/test_equivalencia_sql.py
```

La salida nunca puede quedar dentro del repo ni en una carpeta sincronizada a la nube; la herramienta se niega a escribir ahí. Contiene `reporte.html` (autocontenido, interactivo, con índice), `tablas/*.csv` y, si alguna sección falla, `errores.log`. **El reporte y las tablas llevan información derivada de los datos: no se suben a git, a la nube ni a ninguna IA.** El reporte lleva una marca (`hun-datos`) que hace que el hook anti-fuga lo bloquee si alguien lo intenta commitear.

### Confidencialidad

- `sql/02_cuellos_botella/entrada.sql` es nivel paciente y está marcado con `-- @nivel_paciente`: `hun.extract` se niega a guardarlo en un parquet. Úsenlo solo como `--entrada`.
- `muestra_carriles > 0` dibuja episodios de pacientes individuales en el reporte. La herramienta lo rechaza salvo que se pase `--permitir-carriles`; mientras el HUN no autorice guardar datos por paciente, déjenlo en 0.

## Qué produce

| Sección | Contenido |
|---|---|
| A. Calidad | nulos y tipos, fin < inicio, duración 0, duplicados, solapes (misma zona y entre zonas), cobertura mensual con meses incompletos, duraciones extremas |
| B. Episodios | unión de segmentos por umbral (o columna `caso`), secuencias de zonas, comparación con y sin recorte, carriles opcionales |
| C. Por zona | duración (box log, ECDF, percentiles), entradas y salidas por día × hora, desbalance, acumuladas del día típico |
| D. Censo | censo horario por barrido de eventos, heatmaps de media y p90, distribución, capacidad opcional, censo al llegar, ley de Little |
| E. Transiciones | matriz origen → destino, Sankey, hueco o solape entre zonas por transición, hora y día, reconsultas entre episodios |
| F. Relaciones | duración según hora y día de entrada, hora de salida, censo propio y de la zona siguiente, entradas recientes y destino |
| G. Tiempo | series diarias y semanales con meses incompletos sombreados, perfil por mes del año |
| H. Atributos | duración y destino por grupo (top N + "otros", bins numéricos, tamaño mínimo de grupo) |
| I. Cola larga | curva de Pareto de horas-paciente por zona |

## Definiciones

- **Zonas:** `zonas_incluir` y `zonas_excluir` filtran por el código de la entrada; `zonas_agrupar` une varios códigos en una zona (en el config del repo, 9203 + 3045729 = urgencias y 9201 = hospitalización, como en `_episodios.sql`). Con la agrupación, la marca de llegada solapada con la atención cuenta como solape dentro de la misma zona en la sección A: es esperado.
- **Episodio:** segmentos de una persona que se solapan o están separados por un hueco ≤ `umbral_min`. Se compara contra el máximo fin acumulado, no solo contra el segmento anterior. Da exactamente los mismos episodios que `_episodios.sql`.
- **Estancia:** segmentos seguidos de la misma zona dentro de un episodio, unidos. Es la unidad de las secciones C a I.
- **Recorte:** si una estancia sigue abierta cuando empieza la siguiente del mismo episodio, su fin se corta ahí (como la 25 corta urgencias al ingreso a cama). La comparación con y sin recorte siempre se calcula; `recortar_al_siguiente` decide cuál usa el resto del reporte.
- **Estancias largas:** `excluir_estancias_largas` saca del reporte las estancias más largas que el límite de su zona (7 días urgencias, 90 hospitalización, como la 25). Se aplica después de construir los episodios, así que los episodios no cambian.
- **Episodios irregulares:** una zona aparece más de una vez (p. ej. urgencias → hospitalización → urgencias). Es la única diferencia con el SQL: `_episodios.sql` mide el tiempo en urgencias desde la llegada hasta el último fin de urgencias (incluye el tiempo en cama entre medio) y la 25 cuenta un solo tramo de urgencias por episodio; aquí cada estancia cuenta aparte. El resumen seguro dice cuántos hay.
- **Censo:** personas con una estancia abierta en la zona, con intervalos `[inicio, fin)`. El barrido usa `searchsorted` y sumas acumuladas (O(n log n)), así que aguanta millones de filas.
- **Meses incompletos:** meses con menos filas que `mes_incompleto_frac` × la mediana, o el primer/último mes si el rango de datos cubre menos de `mes_cobertura_min` del mes calendario.

## Módulos

`carga.py` (lectura y esquema interno) · `calidad.py` · `episodios.py` · `censo.py` · `flujos.py` · `transiciones.py` · `relaciones.py` · `tiempo.py` · `atributos.py` · `cola.py` · `figuras.py` (estilo y paleta) · `reporte.py` (HTML) · `resumen_seguro.py`.
