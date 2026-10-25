# Metodología: reconstrucción de episodios de urgencias

## Por qué no usamos `visit_occurrence` directamente

La exploración (consultas `sql/00_exploracion/11` a `18`) mostró que en la base del HUN:

- `visit_occurrence` casi siempre tiene la misma hora de inicio y de fin, así que no sirve para medir duraciones.
- Una misma `visit_occurrence` agrupa segmentos separados por días (por ejemplo, un evento ambulatorio y, días después, una urgencia). No equivale a un episodio de atención.
- Las duraciones reales están en `visit_detail`.

## Cómo está registrado el paso por urgencias

| Concepto | Qué representa en esta base | Duración típica |
|---|---|---|
| 9203 Emergency Room Visit | Marca de llegada/registro | 0 o menos de 15 min, solapada con el inicio de la atención |
| 3045729 Treatment urgency | Estancia en urgencias (atención/observación) | 1–4 h, con cola larga; varios segmentos seguidos |
| 9201 Inpatient Visit | Hospitalización | 1–7 días |
| 581479 Ambulatory Rehabilitation Visit | Eventos ambulatorios puntuales | 0 (fuera del flujo de urgencias) |

El uso de 3045729 como tipo de visita y de segmento es propio del mapeo del HUN (en OMOP estándar es un concepto de observación). Está pendiente confirmarlo con los organizadores.

## Definición de episodio

Implementada en `sql/01_episodios/_episodios.sql`:

1. Se toman los segmentos de `visit_detail` con conceptos 9203, 3045729 y 9201, y se asocian al paciente vía `visit_occurrence`.
2. Por paciente y en orden cronológico, un segmento **continúa** el episodio si empieza antes de que termine lo anterior o con un hueco de hasta `gap_min` minutos (60 por defecto). Si el hueco es mayor, empieza un episodio nuevo (técnica *gaps and islands*).
3. Para cada episodio:
   - **Llegada** = primer inicio de un segmento de urgencias (9203 o 3045729).
   - **Fin de urgencias** = último fin de un segmento de urgencias.
   - **Destino** = `hospitalizado` si el episodio incluye 9201; si no, `alta`.
   - **Tiempo en urgencias** = fin de urgencias − llegada.
   - **Estancia hospitalaria** = último fin de 9201 − primer inicio de 9201.
4. Los episodios que empiezan en hospitalización (sin urgencia previa contigua) se tratan aparte.

## Interpretación clave

Cuando un paciente se hospitaliza, el tiempo entre su llegada y su ingreso a cama incluye la **espera de cama (boarding)**. Por eso la diferencia entre el tiempo en urgencias de hospitalizados y de dados de alta es un indicador del bloqueo por falta de camas.

Hay que medirla bien: la consulta 24 mostró que en bastantes hospitalizados el registro de urgencias **sigue abierto después del ingreso a cama**. Con la definición de arriba (fin de urgencias = último fin de un segmento de urgencias), ese tiempo ya en cama se cuenta como urgencias. Para comparar destinos se usa el tiempo en urgencias **recortado al ingreso**: `LEAST(fin_urg, ini_hosp) − llegada` (consulta 25, `28_tiempos_semanales.sql` y `Cuellos_botella` con `recortar_al_siguiente: true`). La cifra de la consulta 20 sin recorte sobrestima la espera de los hospitalizados.

## Ocupación hora a hora

- `23_ocupacion_por_hora.sql` calcula el censo al cierre de cada hora (entradas acumuladas − salidas acumuladas), para urgencias (llegada → fin de urgencias) y hospitalización (todas las estancias con 9201).
- `25_ocupacion_ajustada.sql` es la versión que se usa: corta urgencias al ingreso a cama (evita contar al mismo paciente en dos sitios) y excluye urgencias de más de 7 días y hospitalizaciones de más de 90 (probables registros sin cerrar).
- Los primeros días de la serie subestiman la ocupación porque no cuentan a quienes ya estaban adentro; se descartan como calentamiento.
- La ocupación absoluta todavía no es comparable con la capacidad (58 cubículos, 64 camas): la base parece cubrir más de lo que esa capacidad describe. Los patrones relativos sí son confiables.

## Episodios irregulares

En unos pocos episodios urgencias reaparece después de la hospitalización (urgencias → hospitalización → urgencias) o la hospitalización va antes que urgencias. El SQL y `Cuellos_botella` los miden distinto (el SQL toma de la primera llegada al último fin de urgencias; la herramienta suma cada estancia). Fuera de ellos coinciden exacto (`Cuellos_botella/tests/test_equivalencia_sql.py`). Qué son en la realidad (registro abierto, traslado de vuelta o error) está pendiente de decidir.

## Series de tiempo

`26_series_horarias.sql` deja las llegadas, ingresos, altas y censos en una rejilla horaria completa (las horas sin eventos salen con 0; la 21 solo trae las horas con llegadas). `series_tiempo/` las usa para el reporte de pronóstico.

## Limitaciones

- No hay nivel de triaje (I–V) ni etapas internas de urgencias (triaje, admisión, consulta).
- `procedure_occurrence` solo tiene fecha (sin hora).
- El umbral de 60 min es una decisión de modelado. `20_resumen_episodios.sql` reporta qué parte de las hospitalizaciones "sin urgencia previa" empieza dentro de las 48 h siguientes a una urgencia, como chequeo de sensibilidad.
- Capacidades de referencia (58 cubículos, 64 camas) tomadas de la visita de campo del 1 de octubre; por confirmar.

## Datos sintéticos

`scripts/generar_sintetico.py` crea en un PostgreSQL **local** una base inventada con esta misma estructura, para desarrollar y probar sin acceder a la base del HUN. Se niega a escribir en un host que no sea local.
