# Exploración inicial de la base (oct 2026)

Consultas que usamos para entender cómo registra el HUN el paso por urgencias. Quedan como evidencia de dónde salen las definiciones de `sql/01_episodios/` y de `docs/METODOLOGIA_EPISODIOS.md`. Todas son agregadas; sus resúmenes en palabras son `scripts/resumen_seguro.py` (02, 08-10), `_2` (11-14) y `_3` (15-18).

| Consulta | Qué responde | Qué mostró (en palabras) |
|---|---|---|
| `00_conteos_tablas` | Cuántos registros tiene cada tabla | Orden de magnitud de cada tabla |
| `01_volumen_por_anio` | Qué años cubre la base | La base llega hasta mediados de 2026; los últimos meses están incompletos |
| `02_tipos_visita_y_etapas` | Qué tipos de visita y de segmento existen | Se usan 9203, 3045729, 9201, 581479 y 0; no aparecen 9202 ni 262 |
| `07_columnas_reales` | Qué columnas existen de verdad | Solo 7 tablas, con diferencias frente al diccionario entregado (ver CLAUDE.md §4) |
| `08_conceptos_triaje` | Si el vocabulario tiene conceptos de triaje | Sí existen en `concept` |
| `09_conceptos_measurement` | Qué se mide en `measurement` | Casi todo laboratorio; parte trae texto libre |
| `10_texto_triaje` | Si el texto libre menciona triaje | ⚠️ Devuelve texto real: solo se mira en local |
| `11_uso_conceptos_triaje` | Si esos conceptos se usan en los datos | "Triage level" no se usa: **no hay nivel de triaje I-V** |
| `12_granularidad_tiempos` | Si las horas son reales | Horas reales (casi ninguna a medianoche); `visit_occurrence` casi siempre tiene inicio = fin |
| `13_visita_vs_segmento` | Qué segmentos hay en cada tipo de visita | Una visita mezcla segmentos de urgencias, hospitalización y ambulatorios |
| `14_segmentos_por_visita` | Cuántos segmentos tiene una visita | Muchas visitas agrupan varios segmentos |
| `15_duracion_por_segmento` | Cuánto dura cada tipo de segmento | 9203 dura 0 o minutos (marca de llegada); 3045729, horas (estancia en urgencias); 9201, días; 581479, siempre 0 |
| `16_primero_ultimo_en_urgencias` | Qué segmento va primero y cuál último | En las visitas con urgencias, el primer segmento suele ser la llegada o la atención de urgencias |
| `17_transiciones` | Qué segmento sigue a cuál y con qué hueco | Urgencias → hospitalización suele ir seguido o solapado; a veces hay huecos de horas |
| `18_visita_vs_segmentos` | Si la visita calza con sus segmentos | Una visita agrupa segmentos separados por días: **no es un episodio** |

De aquí salió la reconstrucción de episodios (`sql/01_episodios/_episodios.sql`).

Se borraron las consultas 03-06 (heatmap por `visit_occurrence`, duración por etapa, trayectorias por visita y búsqueda de triaje): partían de supuestos que la exploración descartó y las reemplazan la 15, la 11, Cuellos_botella y las consultas 21-26.
