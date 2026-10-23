# Cuellos de botella: herramienta exploratoria

Genera gráficas, tablas y métricas a partir de un registro de eventos (persona, zona, inicio, fin) para **buscar dónde se acumula la espera**. No concluye: cada figura explica qué muestra y cómo leerla, y la interpretación queda en manos del equipo.

Es genérica: las zonas se descubren de los datos y todo lo específico (columnas, umbral de episodio, zonas excluidas, capacidades, fechas) va en `config.yaml`.

## Uso

```powershell
pip install -r requirements.txt

# Reporte completo (CSV o Parquet). Sin --salida escribe en DATA_DIR\cuellos_botella_salidas
python -m Cuellos_botella --config Cuellos_botella/config.yaml --entrada <archivo.csv|parquet> [--salida <carpeta>]

# Lo único que se puede compartir con Claude: palabras y franjas, sin cifras
python -m Cuellos_botella.resumen_seguro [--salida <carpeta>]

# Tests (datos mínimos construidos dentro de cada test)
python -m pytest Cuellos_botella/tests
```

La salida nunca puede quedar dentro del repo ni en una carpeta sincronizada a la nube; la herramienta se niega a escribir ahí. Contiene `reporte.html` (autocontenido, interactivo, con índice), `tablas/*.csv` y, si alguna sección falla, `errores.log`. **El reporte y las tablas llevan información derivada de los datos: no se suben a git, a la nube ni a ninguna IA.**

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

- **Episodio:** segmentos de una persona que se solapan o están separados por un hueco ≤ `umbral_min`. Se compara contra el máximo fin acumulado, no solo contra el segmento anterior.
- **Estancia:** segmentos seguidos de la misma zona dentro de un episodio, unidos. Es la unidad de las secciones C a I.
- **Recorte:** si una estancia sigue abierta cuando empieza la siguiente del mismo episodio, su fin se corta ahí. La comparación con y sin recorte siempre se calcula; `recortar_al_siguiente` decide cuál usa el resto del reporte.
- **Censo:** personas con una estancia abierta en la zona, con intervalos `[inicio, fin)`. El barrido usa `searchsorted` y sumas acumuladas (O(n log n)), así que aguanta millones de filas.
- **Meses incompletos:** meses con menos filas que `mes_incompleto_frac` × la mediana, o el primer/último mes si el rango de datos cubre menos de `mes_cobertura_min` del mes calendario.

## Módulos

`carga.py` (lectura y esquema interno) · `calidad.py` · `episodios.py` · `censo.py` · `flujos.py` · `transiciones.py` · `relaciones.py` · `tiempo.py` · `atributos.py` · `cola.py` · `figuras.py` (estilo y paleta) · `reporte.py` (HTML) · `resumen_seguro.py`.
